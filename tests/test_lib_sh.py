"""Tests for scripts/lib.sh."""

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "lib.sh"


def run_helper(script, cwd=None):
    """Source lib.sh and run a snippet, returning (exit status, stdout)."""
    completed = subprocess.run(
        ["sh", "-eu", "-c", f". {LIB}\n{script}"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return completed.returncode, completed.stdout


class ApkbuildFieldTest(unittest.TestCase):
    def write_apkbuild(self, body):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        origin = pathlib.Path(directory.name)
        (origin / "APKBUILD").write_text(body)
        return origin

    def test_strips_surrounding_quotes(self):
        origin = self.write_apkbuild('pkgname="demo"\npkgver="2.5.21"\npkgrel=\'3\'\n')
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

    def test_reads_bare_values(self):
        origin = self.write_apkbuild("pkgname=demo\npkgver=2.5.21\npkgrel=3\n")
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

    def test_formats_declared_and_published_build_identities(self):
        origin = self.write_apkbuild("pkgname=demo\npkgver=2.5.21\npkgrel=3\n")
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as versions:
            self.addCleanup(pathlib.Path(versions.name).unlink)
            versions.write("2.4.0-r1\n2.5.21-r3\n")
            versions.flush()
            status, out = run_helper(
                f'apkbuild_declared_build "{origin}"; '
                f'format_published_builds "{versions.name}"'
            )
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["2.5.21-r3", "2.4.0-r1 2.5.21-r3"])

    def test_ignores_indented_and_suffixed_keys(self):
        # `pkgver_extra=` and an indented assignment inside a build function
        # must not shadow the real top-level field.
        origin = self.write_apkbuild(
            "pkgname=demo\n\tpkgver=nope\npkgver_extra=nope\npkgver=4\npkgrel=1\n"
        )
        status, out = run_helper(f'apkbuild_field pkgver "{origin}/APKBUILD"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "4")

    def test_does_not_execute_apkbuild_contents(self):
        # The reader must never source the APKBUILD. A command substitution has
        # to come back as inert text, not run.
        marker = self.write_apkbuild("") / "should_not_exist"
        origin = self.write_apkbuild(
            f"pkgname=demo\npkgver=$(touch {marker}; echo pwned)\npkgrel=1\n"
        )
        status, out = run_helper(f'apkbuild_field pkgver "{origin}/APKBUILD"')
        self.assertEqual(status, 0)
        self.assertFalse(marker.exists(), "APKBUILD contents were executed")
        self.assertIn("touch", out)


class ChangedOriginsTest(unittest.TestCase):
    def test_lists_origins_for_all_package_input_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = pathlib.Path(directory) / "changed"
            changed.write_text(
                "packages/alpha/APKBUILD\n"
                "packages/alpha/fix.patch\n"
                "packages/beta/service.initd\n"
                "README.md\n"
            )
            status, out = run_helper(f'changed_origins "{changed}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["alpha", "beta"])


class OriginDirectoryTest(unittest.TestCase):
    def test_accepts_directory_named_for_package_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = pathlib.Path(directory) / "demo"
            origin.mkdir()
            (origin / "APKBUILD").write_text("pkgname=demo\n")
            status, _ = run_helper(f'assert_origin_directory "{origin}"')
        self.assertEqual(status, 0)

    def test_rejects_directory_not_named_for_package_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = pathlib.Path(directory) / "wrong"
            origin.mkdir()
            (origin / "APKBUILD").write_text("pkgname=demo\n")
            completed = subprocess.run(
                ["sh", "-eu", "-c", f'. {LIB}\nassert_origin_directory "{origin}"'],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must match pkgname demo", completed.stderr)


class ApkindexTest(unittest.TestCase):
    INDEX = """\
P:gnupg
V:2.5.21-r2
A:x86_64
o:gnupg

P:gpg
V:2.5.21-r2
A:x86_64
o:gnupg

P:zerostack
V:1.7.2-r2
A:x86_64
o:zerostack
"""

    def write_index(self, body=None):
        index = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.addCleanup(pathlib.Path(index.name).unlink)
        index.write(self.INDEX if body is None else body)
        index.close()
        return index.name

    def test_lists_every_indexed_apk(self):
        status, out = run_helper(f'apkindex_apks "{self.write_index()}"')
        self.assertEqual(status, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "gnupg-2.5.21-r2.apk",
                "gpg-2.5.21-r2.apk",
                "zerostack-1.7.2-r2.apk",
            ],
        )

    def test_lists_complete_package_origin_family(self):
        status, out = run_helper(
            f'apkindex_origin_apks "{self.write_index()}" gnupg'
        )
        self.assertEqual(status, 0)
        self.assertEqual(
            out.splitlines(),
            ["gnupg-2.5.21-r2.apk", "gpg-2.5.21-r2.apk"],
        )

    def test_validates_candidate_family_metadata(self):
        candidate = self.INDEX.rsplit("\nP:zerostack", 1)[0]
        status, _ = run_helper(
            f'apkindex_validate_family "{self.write_index(candidate)}" gnupg 2.5.21-r2 x86_64'
        )
        self.assertEqual(status, 0)

    def test_accepts_noarch_package_in_candidate_family(self):
        candidate = self.INDEX.rsplit("\nP:zerostack", 1)[0].replace(
            "A:x86_64", "A:noarch"
        )
        status, _ = run_helper(
            f'apkindex_validate_family "{self.write_index(candidate)}" gnupg 2.5.21-r2 x86_64'
        )
        self.assertEqual(status, 0)

    def test_rejects_foreign_package_in_candidate_family(self):
        status, _ = run_helper(
            f'apkindex_validate_family "{self.write_index()}" gnupg 2.5.21-r2 x86_64'
        )
        self.assertNotEqual(status, 0)

    def test_compares_package_sets_independent_of_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            expected = root / "expected"
            actual = root / "actual"
            expected.write_text("gpg.apk\ngnupg.apk\n")
            actual.write_text("gnupg.apk\ngpg.apk\n")
            status, _ = run_helper(f'package_sets_equal "{expected}" "{actual}"')
        self.assertEqual(status, 0)

    def test_rejects_different_package_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            expected = root / "expected"
            actual = root / "actual"
            expected.write_text("gpg.apk\ngnupg.apk\n")
            actual.write_text("gnupg.apk\n")
            status, _ = run_helper(f'package_sets_equal "{expected}" "{actual}"')
        self.assertNotEqual(status, 0)


class CallerIsolationTest(unittest.TestCase):
    def test_helpers_do_not_clobber_caller_variables(self):
        # The workflows call these from inside `for origin in ...` loops and
        # POSIX sh has no `local`, so a reused name would corrupt iteration
        # while every command still exits zero.
        with tempfile.TemporaryDirectory() as directory:
            tree = pathlib.Path(directory)
            package = tree / "packages" / "alpha"
            package.mkdir(parents=True)
            (package / "APKBUILD").write_text('pkgname=alpha\narch="all"\npkgver=1\npkgrel=0\n')
            script = (
                "origin=caller; arch=caller; name=caller; version=caller\n"
                "all_origins >/dev/null\n"
                "supports_arch x86_64 packages/alpha/APKBUILD || true\n"
                "apkbuild_pinned_spec packages/alpha >/dev/null\n"
                "assert_origin_directory packages/alpha\n"
                'echo "$origin $arch $name $version"'
            )
            status, out = run_helper(script, cwd=tree)
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["caller"] * 4)


class ShellCompatibilityTest(unittest.TestCase):
    def test_library_is_posix_sh_clean(self):
        # The workflows source this from busybox ash, so it must parse without
        # bash extensions.
        completed = subprocess.run(
            ["sh", "-n", str(LIB)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(
        subprocess.run(
            ["sh", "-c", "command -v shellcheck"], capture_output=True
        ).returncode
        == 0,
        "shellcheck not installed",
    )
    def test_shellcheck_is_clean(self):
        completed = subprocess.run(
            ["shellcheck", "--shell=sh", str(LIB)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()
