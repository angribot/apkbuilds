"""Behavior tests for the CI declared-build guard."""

import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "scripts" / "check-declared-build.sh"
LIB = ROOT / "scripts" / "lib.sh"


class DeclaredBuildGuardTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        (self.root / "scripts").mkdir()
        (self.root / "packages" / "alpha").mkdir(parents=True)
        (self.root / "packages" / "beta").mkdir()
        (self.root / "runner-temp").mkdir()
        (self.root / "bin").mkdir()
        (self.root / "scripts" / "check-declared-build.sh").write_bytes(
            CHECK.read_bytes()
        )
        (self.root / "scripts" / "lib.sh").write_bytes(LIB.read_bytes())
        self.write_apkbuild("alpha", "0")
        self.write_apkbuild("beta", "0")
        (self.root / "packages" / "alpha" / "fix.patch").write_text(
            "initial packaging input\n"
        )
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "packages")
        self.git("commit", "-q", "-m", "initial")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

        fake_apk = self.root / "bin" / "apk"
        fake_apk.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = version ] && [ \"$2\" = -t ]; then\n"
            "  [ \"$3\" = 1.0.0-r1 ] && [ \"$4\" = 1.0.0-r0 ] && echo '>' && exit 0\n"
            "  echo '='\n"
            "fi\n"
        )
        fake_apk.chmod(0o755)

    def git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

    def write_apkbuild(self, origin, pkgrel):
        (self.root / "packages" / origin / "APKBUILD").write_text(
            f"pkgname={origin}\npkgver=1.0.0\npkgrel={pkgrel}\n"
        )

    def run_guard(self):
        env = os.environ.copy()
        env.update(
            {
                "BASE_SHA": self.base,
                "RUNNER_TEMP": str(self.root / "runner-temp"),
                "PATH": f"{self.root / 'bin'}:{env['PATH']}",
            }
        )
        return subprocess.run(
            ["sh", "scripts/check-declared-build.sh"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_auxiliary_input_without_declared_build_increase_fails(self):
        (self.root / "packages" / "alpha" / "fix.patch").write_text(
            "changed packaging input\n"
        )

        completed = self.run_guard()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("alpha must increase pkgver or pkgrel", completed.stderr)
        self.assertIn("1.0.0-r0 -> 1.0.0-r0", completed.stderr)

    def test_auxiliary_input_with_declared_build_increase_passes(self):
        (self.root / "packages" / "alpha" / "fix.patch").write_text(
            "changed packaging input\n"
        )
        self.write_apkbuild("alpha", "1")

        completed = self.run_guard()

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_deleted_package_origin_fails_with_actionable_error(self):
        self.git("rm", "-q", "-r", "packages/alpha")

        completed = self.run_guard()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("alpha changed package inputs but has no APKBUILD", completed.stderr)

    def test_renamed_package_input_checks_the_source_origin(self):
        self.git(
            "mv",
            "packages/alpha/fix.patch",
            "packages/beta/fix.patch",
        )

        completed = self.run_guard()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("alpha must increase pkgver or pkgrel", completed.stderr)


if __name__ == "__main__":
    unittest.main()
