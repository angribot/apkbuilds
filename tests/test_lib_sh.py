"""Tests for scripts/lib.sh.

The shell helpers gate which architectures a package is built and published
for, so a silent regression there means either a missing package or a bogus
publication. They ran untested while three copies of supports_arch() drifted
apart, so they get direct coverage here.
"""

import os
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


class SupportsArchTest(unittest.TestCase):
    def assert_supports(self, arch, arch_line, expected):
        with tempfile.TemporaryDirectory() as directory:
            apkbuild = pathlib.Path(directory) / "APKBUILD"
            apkbuild.write_text(f"pkgname=demo\n{arch_line}pkgver=1\n")
            status, _ = run_helper(f'supports_arch {arch} "{apkbuild}"')
        verb = "support" if expected else "reject"
        self.assertEqual(
            status == 0,
            expected,
            f"expected {arch_line.strip() or '<no arch line>'} to {verb} {arch}",
        )

    def test_absent_or_empty_arch_is_unrestricted(self):
        self.assert_supports("x86_64", "", True)
        self.assert_supports("x86_64", 'arch=""\n', True)

    def test_all_and_noarch_match_every_arch(self):
        self.assert_supports("x86_64", 'arch="all"\n', True)
        self.assert_supports("riscv64", 'arch="all"\n', True)
        self.assert_supports("aarch64", 'arch="noarch"\n', True)

    def test_explicit_list_matches_only_listed_arches(self):
        self.assert_supports("x86_64", 'arch="x86_64 aarch64"\n', True)
        self.assert_supports("riscv64", 'arch="x86_64 aarch64"\n', False)

    def test_negation_excludes_only_the_negated_arch(self):
        self.assert_supports("aarch64", 'arch="all !aarch64"\n', False)
        self.assert_supports("x86_64", 'arch="all !aarch64"\n', True)

    def test_unquoted_and_single_quoted_arch_are_parsed(self):
        # Both forms are legal in an APKBUILD; treating them as an absent arch
        # line would wrongly report every arch as supported.
        self.assert_supports("x86_64", "arch=noarch\n", True)
        self.assert_supports("riscv64", "arch=x86_64\n", False)
        self.assert_supports("x86_64", "arch='x86_64 aarch64'\n", True)
        self.assert_supports("riscv64", "arch='x86_64 aarch64'\n", False)

    def test_negation_beats_explicit_listing(self):
        # abuild treats the exclusion as authoritative even when the arch is
        # also named, so a contradictory line must not build.
        self.assert_supports("aarch64", 'arch="aarch64 !aarch64"\n', False)

    def test_substring_arch_does_not_match(self):
        # "x86" must not satisfy a request for "x86_64" via prefix matching.
        self.assert_supports("x86_64", 'arch="x86"\n', False)


class OriginHelpersTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tree = pathlib.Path(self.directory.name)
        self.write_package("alpha", 'arch="all"')
        self.write_package("beta", 'arch="x86_64"')
        self.write_package("gamma", 'arch="all !aarch64"')

    def write_package(self, origin, arch_line):
        package = self.tree / "packages" / origin
        package.mkdir(parents=True)
        (package / "APKBUILD").write_text(f"pkgname={origin}\n{arch_line}\n")

    def test_all_origins_is_sorted_and_complete(self):
        status, out = run_helper("all_origins", cwd=self.tree)
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["alpha", "beta", "gamma"])

    def test_all_origins_ignores_nested_directories(self):
        nested = self.tree / "packages" / "alpha" / "subdir"
        nested.mkdir()
        (nested / "APKBUILD").write_text("pkgname=nope\n")
        status, out = run_helper("all_origins", cwd=self.tree)
        self.assertEqual(status, 0)
        self.assertNotIn("alpha/subdir", out.split())

    def test_origins_for_arch_filters_by_declared_support(self):
        # alpha=all, beta=x86_64 only, gamma=all but negates aarch64.
        for arch, expected in [
            ("x86_64", ["alpha", "beta", "gamma"]),
            ("aarch64", ["alpha"]),
            ("riscv64", ["alpha", "gamma"]),
        ]:
            with self.subTest(arch=arch):
                status, out = run_helper(f"origins_for_arch {arch}", cwd=self.tree)
                self.assertEqual(status, 0)
                self.assertEqual(out.split(), expected)

    def test_helpers_do_not_clobber_caller_variables(self):
        # The workflows call these from inside `for origin in ...` loops and
        # POSIX sh has no `local`, so the helpers must not reuse caller names.
        script = (
            'origin=caller; arch=caller; name=caller; version=caller\n'
            'origins_for_arch x86_64 >/dev/null\n'
            'supports_arch x86_64 packages/alpha/APKBUILD || true\n'
            'apkbuild_pinned_spec packages/alpha >/dev/null\n'
            'echo "$origin $arch $name $version"'
        )
        status, out = run_helper(script, cwd=self.tree)
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["caller"] * 4)

    def test_origins_for_arch_is_empty_when_all_packages_are_restricted(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = pathlib.Path(directory)
            package = tree / "packages" / "only-x86"
            package.mkdir(parents=True)
            (package / "APKBUILD").write_text('pkgname=only-x86\narch="x86_64"\n')
            status, out = run_helper("origins_for_arch aarch64", cwd=tree)
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), [])


class ApkbuildFieldTest(unittest.TestCase):
    def write_apkbuild(self, body):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        origin = pathlib.Path(directory.name)
        (origin / "APKBUILD").write_text(body)
        return origin

    def test_strips_surrounding_quotes(self):
        # Quoted values must not leak quotes into an `apk add` version pin.
        origin = self.write_apkbuild(
            'pkgname="demo"\npkgver="2.5.21"\npkgrel=\'3\'\n'
        )
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

    def test_reads_scalar_fields(self):
        origin = self.write_apkbuild("pkgname=demo\npkgver=2.5.21\npkgrel=3\n")
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=2.5.21-r3")

    def test_ignores_later_duplicate_assignments(self):
        origin = self.write_apkbuild("pkgname=demo\npkgver=1\npkgrel=0\npkgver=9\n")
        status, out = run_helper(f'apkbuild_pinned_spec "{origin}"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "demo=1-r0")
    def test_ignores_indented_and_suffixed_keys(self):
        origin = self.write_apkbuild(
            "pkgname=demo\n\tpkgver=nope\npkgver_extra=nope\npkgver=4\npkgrel=1\n"
        )
        status, out = run_helper(f'apkbuild_field pkgver "{origin}/APKBUILD"')
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "4")

    def test_does_not_execute_apkbuild_contents(self):
        # The reader must never source the APKBUILD. A command substitution in
        # the file has to come back as inert text, not run.
        marker = self.write_apkbuild("") / "should_not_exist"
        origin = self.write_apkbuild(
            f"pkgname=demo\npkgver=$(touch {marker}; echo pwned)\npkgrel=1\n"
        )
        status, out = run_helper(f'apkbuild_field pkgver "{origin}/APKBUILD"')
        self.assertEqual(status, 0)
        self.assertFalse(marker.exists(), "APKBUILD contents were executed")
        self.assertIn("touch", out)


class SplitOriginsTest(unittest.TestCase):
    def test_splits_comma_separated_list(self):
        for value, expected in [
            ("alpha,beta,gamma", ["alpha", "beta", "gamma"]),
            ("alpha", ["alpha"]),
            ("", []),
        ]:
            with self.subTest(value=value):
                status, out = run_helper(f'split_origins "{value}"')
                self.assertEqual(status, 0)
                self.assertEqual(out.split(), expected)


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
