"""Tests for scripts/lib.sh.

Scope rule: cover only the helpers whose failure leaves CI green while the
behaviour is wrong. A bad .apk filename or a leaked quote makes the build job
miss a published package and rebuild silently, or makes `apk add` fail to pin
a version. Mistakes that abort abuild or `apk verify` need no test here,
because the workflow already turns red.
"""

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
    """The field reader feeds every version pin and filename."""

    def write_apkbuild(self, body):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        origin = pathlib.Path(directory.name)
        (origin / "APKBUILD").write_text(body)
        return origin

    def test_strips_surrounding_quotes(self):
        # A leaked quote would produce `demo="2.5.21"-r3`, which never matches
        # a published filename, so the package rebuilds on every run.
        origin = self.write_apkbuild('pkgname="demo"\npkgver="2.5.21"\npkgrel=\'3\'\n')
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

    def test_reads_bare_values(self):
        origin = self.write_apkbuild("pkgname=demo\npkgver=2.5.21\npkgrel=3\n")
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

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


class PinnedApkTest(unittest.TestCase):
    def test_filename_matches_abuild_output(self):
        # The build job probes the published repository for this exact name to
        # decide whether an origin still needs building.
        with tempfile.TemporaryDirectory() as directory:
            origin = pathlib.Path(directory)
            (origin / "APKBUILD").write_text(
                'pkgname=gnupg\npkgver="2.5.21"\npkgrel=1\n'
            )
            status, out = run_helper(f'apkbuild_pinned_apk "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "gnupg-2.5.21-r1.apk")


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
                "apkbuild_pinned_apk packages/alpha >/dev/null\n"
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
