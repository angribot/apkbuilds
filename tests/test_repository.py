import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "repository", Path(__file__).parents[1] / "scripts/repository.py"
)
repository = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repository)


def package(name, version, origin, checksum):
    return repository.Package(name, version, origin, checksum)


def index_file(directory, packages, name="APKINDEX.tar.gz"):
    contents = "\n\n".join(
        f"C:{item.checksum}\nP:{item.name}\nV:{item.version}\no:{item.origin}"
        for item in packages
    ) + "\n"
    path = Path(directory) / name
    data = contents.encode()
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("APKINDEX")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return path


class RepositoryTest(unittest.TestCase):
    def test_scope_selects_changed_source_packages(self):
        self.assertEqual(
            repository.package_origins(
                (path for path in ["README.md", "packages/zerostack/APKBUILD", "packages/gnupg/fix-i18n.patch"])
            ),
            ["gnupg", "zerostack"],
        )

    def test_verify_pkgrel_requires_reset_for_upstream_updates_and_increment_for_rebuilds(self):
        repository.verify_pkgrel(("2.5.21", 1), ("2.5.21", 2))
        repository.verify_pkgrel(("2.5.21", 1), ("2.5.22", 0))
        with self.assertRaisesRegex(ValueError, "must increase"):
            repository.verify_pkgrel(("2.5.21", 1), ("2.5.21", 1))
        with self.assertRaisesRegex(ValueError, "must be 0"):
            repository.verify_pkgrel(("2.5.21", 1), ("2.5.22", 1))

    def test_retained_packages_excludes_selected_origin(self):
        packages = {
            "gpg": package("gpg", "2.5.21-r1", "gnupg", "Q1gpg"),
            "zerostack": package("zerostack", "1.7.1-r0", "zerostack", "Q1zero"),
        }
        self.assertEqual(
            repository.retained_packages(packages, {"gnupg"}),
            {"zerostack": packages["zerostack"]},
        )

    def test_verify_retained_rejects_rebuilt_package(self):
        with tempfile.TemporaryDirectory() as directory:
            old = index_file(
                directory,
                [
                    package("gpg", "2.5.21-r1", "gnupg", "Q1oldgpg"),
                    package("zerostack", "1.7.1-r0", "zerostack", "Q1oldzero"),
                ],
            )
            retained = index_file(
                directory,
                [package("zerostack", "1.7.1-r0", "zerostack", "Q1different")],
                "retained.tar.gz",
            )
            with self.assertRaisesRegex(ValueError, "retained package changed"):
                repository.verify_retained(
                    repository.read_index(old),
                    repository.read_index(retained),
                    {"gnupg"},
                )

    def test_replacements_require_selected_origins_and_report_versions(self):
        old = {
            "gpg": package("gpg", "2.5.21-r1", "gnupg", "Q1old"),
            "zerostack": package("zerostack", "1.7.1-r0", "zerostack", "Q1zero"),
        }
        new = {"gpg": package("gpg", "2.5.22-r0", "gnupg", "Q1new")}
        self.assertEqual(
            repository.replacements(old, new, {"gnupg"}),
            [("gpg", "2.5.22-r0", "2.5.21-r1")],
        )
        with self.assertRaisesRegex(ValueError, "unexpected origins"):
            repository.replacements(old, {"zerostack": old["zerostack"]}, {"gnupg"})

    def test_read_index_rejects_missing_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "APKINDEX.tar.gz"
            data = b"C:Q1checksum\nP:gpg\nV:2.5.21-r1\n"
            with tarfile.open(path, "w:gz") as archive:
                member = tarfile.TarInfo("APKINDEX")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "missing o"):
                repository.read_index(path)


if __name__ == "__main__":
    unittest.main()
