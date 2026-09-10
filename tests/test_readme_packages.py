"""Guard the README available-packages table against APKBUILD drift."""

import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _field(text, name):
    match = re.search(rf"^{re.escape(name)}=(.*)$", text, re.MULTILINE)
    if match is None:
        return ""
    value = match.group(1)
    quote = value[:1]
    if quote in ("'", '"') and not (len(value) > 1 and value.endswith(quote)):
        tail = text[match.end():]
        close = tail.find(quote)
        value += tail[: close + 1] if close != -1 else tail
    value = value.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        value = value[1:]
        if value.endswith(quote):
            value = value[:-1]
    return value


def apkbuild_declarations(text):
    """Return the installable package names an APKBUILD text declares.

    Like `apkbuild_field` in scripts/lib.sh, reads declarations without
    executing the APKBUILD; unlike it, handles multi-line values and
    `$pkgname` expansion.
    """
    pkgname = _field(text, "pkgname")
    names = {pkgname}
    for token in _field(text, "subpackages").split():
        token = token.replace("${pkgname}", pkgname).replace("$pkgname", pkgname)
        names.add(token.split(":", 1)[0])
    return names


_ROW = re.compile(
    r"^\|\s*\[`(?P<origin>[^`]+)`\]\(packages/[^)]*?\)\s*\|"
    r"(?P<packages>[^|]*)\|"
)


def readme_table(text):
    """Return README's available-packages table as origin -> package names."""
    section = text.split("## Available packages", 1)[1].split("\n## ", 1)[0]
    table = {}
    for line in section.splitlines():
        match = _ROW.match(line)
        if match is not None:
            table[match.group("origin")] = set(
                re.findall(r"`([^`]+)`", match.group("packages"))
            )
    return table


def table_drift(packages_dir, readme_text):
    """Report installable packages the README table and APKBUILDs disagree on."""
    declared = {
        path.parent.name: apkbuild_declarations(path.read_text())
        for path in sorted(pathlib.Path(packages_dir).glob("*/APKBUILD"))
    }
    documented = readme_table(readme_text)
    problems = []
    for origin in sorted(set(declared) | set(documented)):
        if origin not in documented:
            problems.append(
                f"{origin}: package origin is missing from the README table"
            )
        elif origin not in declared:
            problems.append(
                f"{origin}: README row has no packages/{origin}/APKBUILD"
            )
        else:
            for name in sorted(declared[origin] - documented[origin]):
                problems.append(f"{origin}: declared but not documented: {name}")
            for name in sorted(documented[origin] - declared[origin]):
                problems.append(f"{origin}: documented but not declared: {name}")
    return problems


class ApkbuildDeclarationsTest(unittest.TestCase):
    def test_reads_pkgname_and_subpackages(self):
        text = (
            'pkgname=alpha\npkgver=1.0.0\npkgrel=0\n'
            'arch="all"\nsubpackages="$pkgname-doc $pkgname-openrc"\n'
        )

        self.assertEqual(
            {"alpha", "alpha-doc", "alpha-openrc"},
            apkbuild_declarations(text),
        )

    def test_reads_multiline_quoted_subpackages(self):
        text = (
            "pkgname=alpha\n"
            'subpackages="\n'
            "\t$pkgname-doc\n"
            "\t$pkgname-lang::noarch\n"
            "\t$pkgname-utils:_utils\n"
            '\t"\n'
            "pkgver=1.0.0\n"
        )

        self.assertEqual(
            {"alpha", "alpha-doc", "alpha-lang", "alpha-utils"},
            apkbuild_declarations(text),
        )

    def test_origin_without_subpackages_declares_only_pkgname(self):
        text = "pkgname=alpha\npkgver=1.0.0\npkgrel=0\n"

        self.assertEqual({"alpha"}, apkbuild_declarations(text))

    def test_value_with_unterminated_quote_reads_to_end(self):
        text = 'pkgname=alpha\nsubpackages="$pkgname-doc\n$pkgname-utils\n'

        self.assertEqual(
            {"alpha", "alpha-doc", "alpha-utils"},
            apkbuild_declarations(text),
        )

    def test_does_not_execute_apkbuild(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = pathlib.Path(directory) / "executed"
            text = f'pkgname=alpha\nsubpackages="$pkgname-doc $(touch {marker})"\n'

            declarations = apkbuild_declarations(text)
            marker_exists = marker.exists()

        self.assertFalse(marker_exists, "APKBUILD contents were executed")
        self.assertIn("alpha", declarations)


class ReadmeTableTest(unittest.TestCase):
    def test_reads_origin_rows_and_installable_packages(self):
        text = (
            "## Available packages\n"
            "\n"
            "| Package origin | Installable packages | Description |\n"
            "| --- | --- | --- |\n"
            "| [`alpha`](packages/alpha/) | `alpha`, `alpha-doc` | Alpha |\n"
            "| [`beta`](packages/beta/) | `beta` | Beta |\n"
            "\n"
            "## Next section\n"
        )

        self.assertEqual(
            {"alpha": {"alpha", "alpha-doc"}, "beta": {"beta"}},
            readme_table(text),
        )

    def test_ignores_tables_outside_the_available_packages_section(self):
        text = (
            "## Available packages\n"
            "\n"
            "| Package origin | Installable packages | Description |\n"
            "| --- | --- | --- |\n"
            "| [`alpha`](packages/alpha/) | `alpha` | Alpha |\n"
            "\n"
            "## Other\n"
            "\n"
            "| Package origin | Installable packages | Description |\n"
            "| [`gamma`](packages/gamma/) | `gamma` | Gamma |\n"
        )

        self.assertEqual({"alpha": {"alpha"}}, readme_table(text))


class TableDriftTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        (self.root / "packages").mkdir()

    def write_apkbuild(self, origin, body):
        directory = self.root / "packages" / origin
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "APKBUILD").write_text(body)

    def readme(self, rows):
        body = "".join(
            f"| [`{origin}`](packages/{origin}/) | "
            + ", ".join(f"`{name}`" for name in names)
            + " | Description |\n"
            for origin, names in rows
        )
        return (
            "## Available packages\n\n"
            "| Package origin | Installable packages | Description |\n"
            "| --- | --- | --- |\n"
            + body
        )

    def run_guard(self, readme_text):
        return table_drift(self.root / "packages", readme_text)

    def test_matching_table_reports_no_drift(self):
        self.write_apkbuild("alpha", "pkgname=alpha\nsubpackages=$pkgname-doc\n")

        problems = self.run_guard(
            self.readme([("alpha", ["alpha", "alpha-doc"])])
        )

        self.assertEqual([], problems)

    def test_declared_package_missing_from_table_is_reported(self):
        self.write_apkbuild("alpha", "pkgname=alpha\nsubpackages=$pkgname-doc")

        problems = self.run_guard(self.readme([("alpha", ["alpha"])]))

        self.assertEqual(1, len(problems))
        self.assertIn("alpha-doc", problems[0])
        self.assertIn("not documented", problems[0])

    def test_documented_package_missing_from_declaration_is_reported(self):
        self.write_apkbuild("alpha", "pkgname=alpha\n")

        problems = self.run_guard(self.readme([("alpha", ["alpha", "alpha-doc"])]))

        self.assertEqual(1, len(problems))
        self.assertIn("alpha-doc", problems[0])
        self.assertIn("not declared", problems[0])

    def test_origin_missing_from_table_is_reported(self):
        self.write_apkbuild("alpha", "pkgname=alpha\n")

        problems = self.run_guard(self.readme([]))

        self.assertEqual(1, len(problems))
        self.assertIn("alpha", problems[0])

    def test_table_row_without_package_origin_is_reported(self):
        problems = self.run_guard(self.readme([("alpha", ["alpha"])]))

        self.assertEqual(1, len(problems))
        self.assertIn("alpha", problems[0])


class RealRepositoryTest(unittest.TestCase):
    def test_readme_table_matches_the_declared_installable_packages(self):
        problems = table_drift(ROOT / "packages", (ROOT / "README.md").read_text())

        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
