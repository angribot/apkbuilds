"""Behavior tests for the public CI operation-module interfaces."""

import os
import pathlib
import shutil
import stat
import subprocess
import tarfile
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODULES = {
    "build": SCRIPTS / "build-package-family.sh",
    "sign": SCRIPTS / "sign-repository.sh",
    "verify": SCRIPTS / "verify-repository.sh",
}


def write_executable(path, body):
    path.write_text(textwrap.dedent(body).lstrip())
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def install_fake_docker(fake_bin):
    """Install a local adapter that can run mounted operation scripts directly."""
    write_executable(
        fake_bin / "docker",
        r'''
        #!/usr/bin/env python3
        import os
        import pathlib
        import subprocess
        import sys

        args = sys.argv[1:]
        if not args:
            raise SystemExit(2)
        if args[0] == "build":
            raise SystemExit(int(os.environ.get("FAKE_DOCKER_BUILD_EXIT", "0")))
        if args[0] != "run":
            raise SystemExit(2)

        count_path = pathlib.Path(os.environ["FAKE_DOCKER_RUN_COUNT"])
        count = int(count_path.read_text()) + 1 if count_path.exists() else 1
        count_path.write_text(str(count))

        mounts = {}
        network = None
        cwd = None
        index = 1
        while index < len(args):
            argument = args[index]
            if argument == "--rm":
                index += 1
            elif argument == "--network":
                network = args[index + 1]
                index += 2
            elif argument == "-v":
                source, target, *_ = args[index + 1].split(":")
                mounts[target] = source
                index += 2
            elif argument == "-w":
                cwd = args[index + 1]
                index += 2
            elif argument == "-e":
                index += 2
            else:
                break

        if os.environ.get("FAKE_DOCKER_ENFORCE_KEY_ISOLATION") == "1":
            if "ABUILD_PRIVATE_KEY" in os.environ:
                print("private key secret reached the container adapter", file=sys.stderr)
                raise SystemExit(96)
            has_private_key = "/private-key" in mounts
            if has_private_key and network != "none":
                print("private key entered a networked container", file=sys.stderr)
                raise SystemExit(97)

        failed_run = int(os.environ.get("FAKE_DOCKER_FAIL_RUN", "0"))
        if failed_run == count:
            raise SystemExit(int(os.environ.get("FAKE_DOCKER_RUN_EXIT", "1")))
        if os.environ.get("FAKE_DOCKER_PASSTHROUGH") != "1":
            raise SystemExit(0)

        index += 1  # image
        command = args[index]
        command_args = args[index + 1 :]

        def translate(value):
            for target in sorted(mounts, key=len, reverse=True):
                if value == target or value.startswith(target + "/"):
                    return mounts[target] + value[len(target) :]
            return value

        environment = os.environ.copy()
        names = {
            "/pages": "APKBUILDS_PAGES",
            "/built": "APKBUILDS_BUILT",
            "/workspace": "APKBUILDS_WORKSPACE",
            "/keys/apkbuilds.rsa.pub": "APKBUILDS_REPOSITORY_KEY",
            "/private-key": "APKBUILDS_PRIVATE_KEY",
            "/new": "APKBUILDS_OUTPUT",
        }
        for target, name in names.items():
            if target in mounts:
                environment[name] = mounts[target]
        container_temp = pathlib.Path(os.environ["RUNNER_TEMP"]) / "container"
        container_temp.mkdir(parents=True, exist_ok=True)
        environment.update(
            {
                "TMPDIR": str(container_temp),
                "APKBUILDS_KEY_DIRECTORY": str(container_temp / "keys"),
                "APKBUILDS_REPOSITORIES_FILE": str(container_temp / "repositories"),
            }
        )
        completed = subprocess.run(
            ["sh", translate(command), *map(translate, command_args)],
            cwd=translate(cwd) if cwd else None,
            env=environment,
        )
        raise SystemExit(completed.returncode)
        ''',
    )


class CiModuleTest(unittest.TestCase):
    def environment(self, root, workspace, fake_bin):
        runner_temp = root / "runner"
        runner_temp.mkdir()
        output = root / "github-output"
        env = os.environ.copy()
        env.update(
            {
                "GITHUB_WORKSPACE": str(workspace),
                "RUNNER_TEMP": str(runner_temp),
                "GITHUB_OUTPUT": str(output),
                "FAKE_DOCKER_RUN_COUNT": str(root / "docker-runs"),
                "PATH": os.pathsep.join([str(fake_bin), env["PATH"]]),
            }
        )
        return env, runner_temp, output

    def workspace(self, root, origin="alpha"):
        workspace = root / "workspace"
        shutil.copytree(SCRIPTS, workspace / "scripts")
        (workspace / "keys").mkdir()
        (workspace / "keys" / "apkbuilds.rsa.pub").write_text("public\n")
        package = workspace / "packages" / origin
        package.mkdir(parents=True)
        (package / "APKBUILD").write_text(
            f"pkgname={origin}\npkgver=1\npkgrel=0\n"
        )
        return workspace

    def test_module_interfaces_expose_only_domain_inputs(self):
        expected_usage = {
            "build": (
                "usage: build-package-family.sh --origin ORIGIN --arch ARCH "
                "--source-revision REVISION --published URL"
            ),
            "sign": "usage: sign-repository.sh",
            "verify": (
                "usage: verify-repository.sh --arch ARCH|all "
                "[--install-declared-builds]"
            ),
        }
        obsolete_inputs = (
            "--workspace",
            "--output",
            "--repository-key",
            "--distfiles",
            "--cargo-home",
            "--ccache-dir",
            "--sccache-dir",
            "--pages",
            "--private-key-file",
            "--key-directory",
            "--repositories-file",
            "--force-build",
        )

        for name, path in MODULES.items():
            with self.subTest(module=name):
                completed = subprocess.run(
                    ["sh", str(path), "--help"], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.strip(), expected_usage[name])
                for obsolete_input in obsolete_inputs:
                    self.assertNotIn(obsolete_input, completed.stdout)

    def test_all_operation_scripts_are_valid_posix_shell(self):
        paths = [*MODULES.values(), *(SCRIPTS / "operations").glob("*.sh")]
        for path in paths:
            with self.subTest(module=path.relative_to(ROOT)):
                completed = subprocess.run(
                    ["sh", "-n", str(path)], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_build_module_reports_a_toolchain_failure_with_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root, "demo")
            write_executable(workspace / "scripts" / "prepare-builder.sh", "exit 1\n")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            env, _, _ = self.environment(root, workspace, fake_bin)
            env["FAKE_DOCKER_PASSTHROUGH"] = "1"
            completed = subprocess.run(
                [
                    "sh",
                    str(MODULES["build"]),
                    "--origin",
                    "demo",
                    "--arch",
                    "x86_64",
                    "--source-revision",
                    "revision",
                    "--published",
                    "https://example.invalid/edge/x86_64",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("stage=toolchain", completed.stderr)
        self.assertIn("arch=x86_64", completed.stderr)
        self.assertIn("package-origin=demo", completed.stderr)

    def test_build_module_stages_a_complete_split_family(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            write_executable(workspace / "scripts" / "prepare-builder.sh", "exit 0\n")
            index_dir = root / "index"
            index_dir.mkdir()
            (index_dir / "APKINDEX").write_text(
                "P:old-alpha\nV:0-r0\nA:x86_64\no:alpha\n"
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            write_executable(fake_bin / "apk", "exit 0\n")
            write_executable(
                fake_bin / "cp",
                r'''
                case "$*" in
                  */etc/apk/keys/*) exit 0 ;;
                  *) exec /bin/cp "$@" ;;
                esac
                ''',
            )
            write_executable(
                fake_bin / "su",
                r'''
                case "$*" in
                  *CARGO_HOME*|*SCCACHE_DIR*|*RUSTC_WRAPPER*) exit 98 ;;
                  *abuild\ listpkg*)
                    printf '%s\n' alpha-1-r0.apk alpha-tools-1-r0.apk
                    ;;
                  *abuild\ -r*)
                    built="$APKBUILDS_OUTPUT/alpha/packages/x86_64"
                    mkdir -p "$built"
                    : > "$built/alpha-1-r0.apk"
                    : > "$built/alpha-tools-1-r0.apk"
                    ;;
                esac
                exit 0
                ''',
            )
            write_executable(
                fake_bin / "wget",
                r'''
                output=
                while [ "$#" -gt 0 ]; do
                  if [ "$1" = -O ]; then output=$2; shift 2; continue; fi
                  shift
                done
                case "$output" in
                  */APKINDEX.tar.gz)
                    tar -czf "$output" -C "$FAKE_INDEX" APKINDEX
                    ;;
                  *) printf '%s\n' package > "$output" ;;
                esac
                ''',
            )
            env, _, github_output = self.environment(root, workspace, fake_bin)
            env.update(
                {
                    "FAKE_DOCKER_PASSTHROUGH": "1",
                    "FAKE_INDEX": str(index_dir),
                }
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(MODULES["build"]),
                    "--origin",
                    "alpha",
                    "--arch",
                    "x86_64",
                    "--source-revision",
                    "revision",
                    "--published",
                    "https://example.invalid/edge/x86_64",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            outputs = dict(
                line.split("=", 1) for line in github_output.read_text().splitlines()
            )
            family = pathlib.Path(outputs["artifact"]) / "x86_64" / "alpha"
            self.assertEqual(
                {package.name for package in family.glob("*.apk")},
                {"alpha-1-r0.apk", "alpha-tools-1-r0.apk"},
            )
            self.assertIn("source revision=revision", completed.stdout)
            self.assertIn("declared build=1-r0", completed.stdout)
            self.assertIn("published build(s)=0-r0", completed.stdout)
            self.assertEqual(outputs["built"], "true")

    def write_repository_arch(
        self, root, arch, version, package_contents, packages=("alpha",)
    ):
        repository = root / "runner" / "pages" / "edge" / arch
        repository.mkdir(parents=True)
        records = []
        for package in packages:
            (repository / f"{package}-{version}.apk").write_bytes(package_contents)
            records.append(f"P:{package}\nV:{version}\nA:{arch}\no:alpha\n")
        index = root / f"APKINDEX-{arch}"
        index.write_text("\n".join(records))
        archive_path = repository / "APKINDEX.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(index, arcname="APKINDEX")
        pathlib.Path(f"{archive_path}.signed").touch()
        return repository

    def prepare_staged_repository(self, root):
        return self.write_repository_arch(root, "x86_64", "1-r0", b"not-an-apk")

    def test_verify_module_checks_and_installs_a_declared_build_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            write_executable(
                fake_bin / "apk",
                r'''
                case "$1" in
                  update)
                    count=0
                    [ -f "$APK_UPDATE_COUNT" ] && count=$(cat "$APK_UPDATE_COUNT")
                    printf '%s\n' $((count + 1)) > "$APK_UPDATE_COUNT"
                    exit "${APK_UPDATE_EXIT:-0}"
                    ;;
                  add) printf '%s\n' "$2" > "$APK_ADD_RESULT" ;;
                esac
                exit 0
                ''',
            )
            env, _, _ = self.environment(root, workspace, fake_bin)
            self.prepare_staged_repository(root)
            env.update(
                {
                    "FAKE_DOCKER_PASSTHROUGH": "1",
                    "APK_UPDATE_COUNT": str(root / "update-count"),
                    "APK_ADD_RESULT": str(root / "added"),
                }
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(MODULES["verify"]),
                    "--arch",
                    "x86_64",
                    "--install-declared-builds",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((root / "update-count").read_text().strip(), "1")
            self.assertEqual((root / "added").read_text().strip(), "alpha=1-r0")

    def test_verify_module_does_not_retry_index_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            write_executable(
                fake_bin / "apk",
                r'''
                if [ "$1" = update ]; then
                  count=0
                  [ -f "$APK_UPDATE_COUNT" ] && count=$(cat "$APK_UPDATE_COUNT")
                  printf '%s\n' $((count + 1)) > "$APK_UPDATE_COUNT"
                  exit 1
                fi
                exit 0
                ''',
            )
            env, _, _ = self.environment(root, workspace, fake_bin)
            self.prepare_staged_repository(root)
            env.update(
                {
                    "FAKE_DOCKER_PASSTHROUGH": "1",
                    "APK_UPDATE_COUNT": str(root / "update-count"),
                }
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(MODULES["verify"]),
                    "--arch",
                    "x86_64",
                    "--install-declared-builds",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual((root / "update-count").read_text().strip(), "1")
            self.assertIn("stage=index", completed.stderr)

    def test_sign_module_skips_an_unchanged_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            env, _, github_output = self.environment(root, workspace, fake_bin)
            completed = subprocess.run(
                ["sh", str(MODULES["sign"])],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(github_output.read_text().strip(), "snapshot_created=false")

    def test_sign_module_atomically_replaces_and_verifies_complete_families(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            write_executable(
                fake_bin / "apk",
                r'''
                #!/usr/bin/env python3
                import os
                import pathlib
                import sys
                import tarfile
                import tempfile

                command, *arguments = sys.argv[1:]
                if command == "verify":
                    for argument in arguments:
                        if argument.endswith(".apk"):
                            if not pathlib.Path(argument).read_bytes().startswith(b"signed"):
                                raise SystemExit(1)
                        elif argument.endswith("APKINDEX.tar.gz"):
                            if not pathlib.Path(f"{argument}.signed").exists():
                                raise SystemExit(1)
                    raise SystemExit(0)
                if command != "index":
                    raise SystemExit(0)

                output = None
                architecture = None
                packages = []
                index = 0
                while index < len(arguments):
                    argument = arguments[index]
                    if argument == "--output":
                        output = arguments[index + 1]
                        index += 2
                    elif argument == "--rewrite-arch":
                        architecture = arguments[index + 1]
                        index += 2
                    elif argument.startswith("-"):
                        index += 1
                    else:
                        packages.append(pathlib.Path(argument).resolve())
                        index += 1

                version = "1-r0"
                records = []
                for package in packages:
                    package_arch = architecture
                    if package_arch is None:
                        package_arch = next(
                            part for part in package.parts
                            if part in ("x86_64", "aarch64")
                        )
                    name = package.name.removesuffix(f"-{version}.apk")
                    records.append(
                        f"P:{name}\nV:{version}\nA:{package_arch}\no:alpha\n"
                    )
                pathlib.Path(f"{output}.signed").unlink(missing_ok=True)
                with tempfile.TemporaryDirectory() as directory:
                    apkindex = pathlib.Path(directory) / "APKINDEX"
                    apkindex.write_text("\n".join(records))
                    with tarfile.open(output, "w:gz") as archive:
                        archive.add(apkindex, arcname="APKINDEX")
                ''',
            )
            write_executable(
                fake_bin / "cp",
                r'''
                case "$2" in
                  /etc/apk/keys|/etc/apk/keys/) exit 0 ;;
                  *) exec /bin/cp "$@" ;;
                esac
                ''',
            )
            write_executable(
                fake_bin / "abuild-gzsplit",
                r'''
                cat >/dev/null
                printf '%s\n' control > control.tar.gz
                printf '%s\n' data > data.tar.gz
                ''',
            )
            write_executable(
                fake_bin / "abuild-sign",
                r'''
                for target do :; done
                if [ "$target" = control.tar.gz ]; then
                  { printf '%s\n' signed; cat "$target"; } > "$target.new"
                  mv "$target.new" "$target"
                elif [ "${FAKE_SKIP_INDEX_SIGNATURE:-0}" != 1 ]; then
                  : > "$target.signed"
                fi
                ''',
            )
            env, runner_temp, github_output = self.environment(
                root, workspace, fake_bin
            )
            packages = ("alpha", "alpha-tools")
            for arch in ("x86_64", "aarch64"):
                self.write_repository_arch(
                    root, arch, "0-r0", b"signed baseline", packages
                )
                candidate = runner_temp / "built" / arch / "alpha"
                candidate.mkdir(parents=True)
                for package in packages:
                    (candidate / f"{package}-1-r0.apk").write_bytes(
                        b"unsigned candidate"
                    )
            env.update(
                {
                    "ABUILD_PRIVATE_KEY": "private",
                    "FAKE_DOCKER_PASSTHROUGH": "1",
                    "FAKE_DOCKER_ENFORCE_KEY_ISOLATION": "1",
                }
            )
            completed = subprocess.run(
                ["sh", str(MODULES["sign"])],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            for arch in ("x86_64", "aarch64"):
                repository = runner_temp / "pages" / "edge" / arch
                for package in packages:
                    self.assertFalse((repository / f"{package}-0-r0.apk").exists())
                    self.assertTrue(
                        (repository / f"{package}-1-r0.apk")
                        .read_bytes()
                        .startswith(b"signed")
                    )
            self.assertEqual(github_output.read_text().strip(), "snapshot_created=true")

            unsigned_output = root / "unsigned-index-output"
            env.update(
                {
                    "GITHUB_OUTPUT": str(unsigned_output),
                    "FAKE_SKIP_INDEX_SIGNATURE": "1",
                }
            )
            rejected = subprocess.run(
                ["sh", str(MODULES["sign"])],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(unsigned_output.exists())

    def test_sign_module_confines_and_removes_the_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace = self.workspace(root)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            install_fake_docker(fake_bin)
            env, runner_temp, github_output = self.environment(
                root, workspace, fake_bin
            )
            candidate = runner_temp / "built" / "x86_64" / "alpha"
            candidate.mkdir(parents=True)
            (candidate / "alpha-1-r0.apk").write_bytes(b"candidate")
            env.update(
                {
                    "ABUILD_PRIVATE_KEY": "private",
                    "FAKE_DOCKER_ENFORCE_KEY_ISOLATION": "1",
                }
            )
            completed = subprocess.run(
                ["sh", str(MODULES["sign"])],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            remaining_files = (
                path for path in runner_temp.rglob("*") if path.is_file()
            )
            self.assertNotIn(b"private\n", (path.read_bytes() for path in remaining_files))
            self.assertEqual(github_output.read_text().strip(), "snapshot_created=true")


if __name__ == "__main__":
    unittest.main()
