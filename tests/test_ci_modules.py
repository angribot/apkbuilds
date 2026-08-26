"""Contract tests for the independently runnable CI modules."""

import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODULES = {
    "build": SCRIPTS / "build-package-family.sh",
    "sign": SCRIPTS / "sign-repository.sh",
    "verify": SCRIPTS / "verify-repository.sh",
}


class CiModuleTest(unittest.TestCase):
    def test_modules_are_valid_posix_shell(self):
        for name, path in MODULES.items():
            with self.subTest(module=name):
                completed = subprocess.run(
                    ["sh", "-n", str(path)], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_modules_require_explicit_parameters(self):
        for name, path in MODULES.items():
            with self.subTest(module=name):
                completed = subprocess.run(
                    ["sh", str(path)], capture_output=True, text=True
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("usage:", completed.stderr.lower())

    def test_workflow_delegates_build_sign_and_verify_to_modules(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        for path in MODULES.values():
            self.assertIn(path.name, workflow)
        build_start = workflow.index("  build:")
        sign_start = workflow.index("\n  sign:", build_start)
        verify_start = workflow.index("\n  verify:")
        publish_start = workflow.index("\n  publish:", verify_start)
        build = workflow[build_start:sign_start]
        sign = workflow[sign_start:verify_start]
        verify = workflow[verify_start:publish_start]
        self.assertNotIn("sh -euxc '", build)
        self.assertNotIn("sh -euxc '", sign)
        self.assertNotIn("sh -euxc '", verify)
        self.assertIn("--arch \"$ARCH\"", build)
        self.assertIn("--origin \"$ORIGIN\"", build)
        self.assertIn("--private-key-file /private-key", sign)
        self.assertIn("--network none", sign)
        # Installation retains its existing network access for Alpine
        # dependencies; extraction must not silently change that boundary.
        self.assertNotIn("--network none", verify)

    def test_modules_log_stage_architecture_and_origin_on_failure(self):
        for path in MODULES.values():
            source = path.read_text()
            self.assertIn("stage=", source)
            self.assertIn("arch=", source)
            self.assertIn("package-origin=", source)

    def test_build_module_reports_a_toolchain_failure_with_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "scripts").mkdir()
            (root / "packages" / "demo").mkdir(parents=True)
            (root / "packages" / "demo" / "APKBUILD").write_text(
                "pkgname=demo\npkgver=1\npkgrel=0\n"
            )
            prepare = root / "scripts" / "prepare-builder.sh"
            prepare.write_text("#!/bin/sh\nexit 1\n")
            prepare.chmod(prepare.stat().st_mode | stat.S_IXUSR)
            key = root / "key"
            key.write_text("key\n")
            args = [
                "sh",
                str(SCRIPTS / "build-package-family.sh"),
                "--arch",
                "x86_64",
                "--origin",
                "demo",
                "--published",
                "https://example.invalid/edge/x86_64",
                "--source-revision",
                "revision",
                "--workspace",
                str(root),
                "--output",
                str(root / "output"),
                "--repository-key",
                str(key),
                "--distfiles",
                str(root / "distfiles"),
                "--cargo-home",
                str(root / "cargo"),
                "--ccache-dir",
                str(root / "ccache"),
                "--sccache-dir",
                str(root / "sccache"),
            ]
            completed = subprocess.run(args, capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("stage=toolchain", completed.stderr)
        self.assertIn("arch=x86_64", completed.stderr)
        self.assertIn("package-origin=demo", completed.stderr)

    def test_sign_module_accepts_an_empty_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_cp = fake_bin / "cp"
            fake_cp.write_text(
                "#!/bin/sh\n"
                "if [ \"$2\" = /etc/apk/keys/ ]; then exit 0; fi\n"
                "exec /bin/cp \"$@\"\n"
            )
            fake_cp.chmod(fake_cp.stat().st_mode | stat.S_IXUSR)
            pages = root / "pages"
            pages.mkdir()
            public_key = root / "public-key"
            private_key = root / "private-key"
            public_key.write_text("public\n")
            private_key.write_text("private\n")
            env = os.environ.copy()
            env["PATH"] = os.pathsep.join([str(fake_bin), env["PATH"]])
            completed = subprocess.run(
                [
                    "sh",
                    str(SCRIPTS / "sign-repository.sh"),
                    "--pages",
                    str(pages),
                    "--repository-key",
                    str(public_key),
                    "--private-key-file",
                    str(private_key),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
