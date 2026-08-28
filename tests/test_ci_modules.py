"""Contract tests for the independently runnable CI modules."""

import os
import pathlib
import stat
import subprocess
import tarfile
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

    def test_build_module_stages_a_complete_family(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = root / "workspace"
            (workspace / "scripts").mkdir(parents=True)
            (workspace / "packages" / "alpha").mkdir(parents=True)
            (workspace / "scripts" / "lib.sh").write_text(
                (SCRIPTS / "lib.sh").read_text()
            )
            (workspace / "scripts" / "prepare-builder.sh").write_text(
                "#!/bin/sh\nexit 0\n"
            )
            (workspace / "packages" / "alpha" / "APKBUILD").write_text(
                "pkgname=alpha\npkgver=1\npkgrel=0\n"
            )
            index_dir = root / "index"
            index_dir.mkdir()
            (index_dir / "APKINDEX").write_text(
                "P:old-alpha\nV:0-r0\nA:x86_64\no:alpha\n"
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_apk = fake_bin / "apk"
            fake_apk.write_text("#!/bin/sh\nexit 0\n")
            fake_apk.chmod(fake_apk.stat().st_mode | stat.S_IXUSR)
            fake_cp = fake_bin / "cp"
            fake_cp.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "*/etc/apk/keys/*) exit 0 ;;\n"
                "*) exec /bin/cp \"$@\" ;;\n"
                "esac\n"
            )
            fake_cp.chmod(fake_cp.stat().st_mode | stat.S_IXUSR)
            fake_su = fake_bin / "su"
            fake_su.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_SU_LOG\"\n"
                "case \"$*\" in\n"
                "*abuild\\ listpkg*) printf '%s\\n' alpha-1-r0.apk ;;\n"
                "*abuild\\ -r*)\n"
                "  repo=source\n"
                "  printf '%s\\n' \"$*\" | grep -q '/packages/' && repo=packages\n"
                "  built=\"$FAKE_OUTPUT/alpha/$repo/x86_64\"\n"
                "  mkdir -p \"$built\"; : > \"$built/alpha-1-r0.apk\"\n"
                "  ;;\n"
                "esac\n"
                "exit 0\n"
            )
            fake_su.chmod(fake_su.stat().st_mode | stat.S_IXUSR)
            fake_wget = fake_bin / "wget"
            fake_wget.write_text(
                "#!/bin/sh\n"
                "output=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = -O ]; then output=$2; shift 2; continue; fi\n"
                "  shift\n"
                "done\n"
                "case \"$output\" in\n"
                "*/APKINDEX.tar.gz) tar -czf \"$output\" -C \"$FAKE_INDEX\" APKINDEX ;;\n"
                "*) printf '%s\\n' package > \"$output\" ;;\n"
                "esac\n"
            )
            fake_wget.chmod(fake_wget.stat().st_mode | stat.S_IXUSR)
            fake_du = fake_bin / "du"
            fake_du.write_text("#!/bin/sh\nprintf '%s %s\\n' 0 \"$2\"\n")
            fake_du.chmod(fake_du.stat().st_mode | stat.S_IXUSR)
            key = root / "public-key"
            key.write_text("public\n")
            output = root / "output"
            cache_dirs = [root / name for name in ("distfiles", "cargo", "ccache", "sccache")]
            for cache_dir in cache_dirs:
                cache_dir.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "PATH": os.pathsep.join([str(fake_bin), env["PATH"]]),
                    "FAKE_INDEX": str(index_dir),
                    "FAKE_OUTPUT": str(output),
                    "FAKE_SU_LOG": str(root / "su-log"),
                }
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(SCRIPTS / "build-package-family.sh"),
                    "--arch",
                    "x86_64",
                    "--origin",
                    "alpha",
                    "--published",
                    "https://example.invalid/edge/x86_64",
                    "--source-revision",
                    "revision",
                    "--workspace",
                    str(workspace),
                    "--output",
                    str(output),
                    "--repository-key",
                    str(key),
                    "--distfiles",
                    str(cache_dirs[0]),
                    "--cargo-home",
                    str(cache_dirs[1]),
                    "--ccache-dir",
                    str(cache_dirs[2]),
                    "--sccache-dir",
                    str(cache_dirs[3]),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            self.assertTrue(
                (
                    output
                    / "built"
                    / "x86_64"
                    / "alpha"
                    / "alpha-1-r0.apk"
                ).exists(),
                completed.stdout + completed.stderr,
            )
            self.assertIn(
                "build_seconds=",
                (
                    output / "metrics" / "x86_64" / "alpha" / "build.txt"
                ).read_text(),
            )

    def test_verify_module_reports_a_signature_failure_with_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            pages = root / "pages" / "edge" / "x86_64"
            pages.mkdir(parents=True)
            (pages / "APKINDEX.tar.gz").write_bytes(b"invalid")
            workspace = root / "workspace"
            (workspace / "scripts").mkdir(parents=True)
            (workspace / "scripts" / "lib.sh").write_text(
                (SCRIPTS / "lib.sh").read_text()
            )
            key = root / "public-key"
            key.write_text("public\n")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_apk = fake_bin / "apk"
            fake_apk.write_text("#!/bin/sh\nexit 1\n")
            fake_apk.chmod(fake_apk.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env["PATH"] = os.pathsep.join([str(fake_bin), env["PATH"]])
            completed = subprocess.run(
                [
                    "sh",
                    str(SCRIPTS / "verify-repository.sh"),
                    "--pages",
                    str(root / "pages"),
                    "--workspace",
                    str(workspace),
                    "--arch",
                    "x86_64",
                    "--repository-key",
                    str(key),
                    "--key-directory",
                    str(root / "keys"),
                    "--repositories-file",
                    str(root / "repositories"),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("stage=signature", completed.stderr)
        self.assertIn("arch=x86_64", completed.stderr)
        self.assertIn("package-origin=all", completed.stderr)

    def test_verify_module_checks_and_installs_a_declared_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            pages = root / "pages" / "edge" / "x86_64"
            pages.mkdir(parents=True)
            (pages / "alpha-1-r0.apk").write_bytes(b"not-an-apk")
            index = root / "index"
            index.write_text("P:alpha\nV:1-r0\nA:x86_64\no:alpha\n")
            with tarfile.open(pages / "APKINDEX.tar.gz", "w:gz") as archive:
                archive.add(index, arcname="APKINDEX")
            workspace = root / "workspace"
            (workspace / "scripts").mkdir(parents=True)
            (workspace / "packages" / "alpha").mkdir(parents=True)
            (workspace / "scripts" / "lib.sh").write_text(
                (SCRIPTS / "lib.sh").read_text()
            )
            (workspace / "packages" / "alpha" / "APKBUILD").write_text(
                "pkgname=alpha\npkgver=1\npkgrel=0\n"
            )
            key = root / "public-key"
            key.write_text("public\n")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            apk = fake_bin / "apk"
            apk.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = add ]; then\n"
                "  printf '%s\\n' \"$2\" > \"$APK_ADD_RESULT\"\n"
                "fi\n"
                "exit 0\n"
            )
            apk.chmod(apk.stat().st_mode | stat.S_IXUSR)
            repositories = root / "repositories"
            env = os.environ.copy()
            env.update(
                {
                    "PATH": os.pathsep.join([str(fake_bin), env["PATH"]]),
                    "APK_ADD_RESULT": str(root / "added"),
                    "APK_UPDATE_RETRY_DELAYS": "0",
                }
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(SCRIPTS / "verify-repository.sh"),
                    "--pages",
                    str(root / "pages"),
                    "--workspace",
                    str(workspace),
                    "--arch",
                    "x86_64",
                    "--repository-key",
                    str(key),
                    "--key-directory",
                    str(root / "keys"),
                    "--repositories-file",
                    str(repositories),
                    "--install-declared-builds",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(
                (root / "added").exists(), completed.stdout + completed.stderr
            )
            self.assertEqual((root / "added").read_text().strip(), "alpha=1-r0")

    def test_sign_module_reports_a_package_failure_with_architecture(self):
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
            fake_apk = fake_bin / "apk"
            fake_apk.write_text("#!/bin/sh\nexit 1\n")
            fake_apk.chmod(fake_apk.stat().st_mode | stat.S_IXUSR)
            fake_split = fake_bin / "abuild-gzsplit"
            fake_split.write_text("#!/bin/sh\nexit 1\n")
            fake_split.chmod(fake_split.stat().st_mode | stat.S_IXUSR)
            pages = root / "pages" / "edge" / "x86_64"
            pages.mkdir(parents=True)
            (pages / "demo-1-r0.apk").write_bytes(b"not-an-apk")
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
                    str(root / "pages"),
                    "--repository-key",
                    str(public_key),
                    "--private-key-file",
                    str(private_key),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("stage=package-signing", completed.stderr)
        self.assertIn("arch=x86_64", completed.stderr)
        self.assertIn("package-origin=all", completed.stderr)

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
