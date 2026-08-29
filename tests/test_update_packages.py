"""Behavior tests for the single-writer package updater."""

import os
import pathlib
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

from tests.update_manifest import read_manifest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update-packages.sh"

PACKAGE_ORIGINS = read_manifest()


class UpdatePackagesTest(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def remote_git(self, remote, *args):
        return subprocess.run(
            ["git", f"--git-dir={remote}", *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def create_checkout(self, entries=PACKAGE_ORIGINS):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        (root / "scripts").mkdir()
        (root / "packages").mkdir()
        shutil.copy(SCRIPT, root / "scripts/update-packages.sh")
        mode = (root / "scripts/update-packages.sh").stat().st_mode
        (root / "scripts/update-packages.sh").chmod(mode | stat.S_IXUSR)
        (root / "packages/updaters").write_text(
            "# package-origin|updater\n"
            + "".join("|".join(entry) + "\n" for entry in entries)
        )
        (root / "README").write_text("initial\n")

        for package_origin, updater in entries:
            apkbuild_path = root / "packages" / package_origin / "APKBUILD"
            apkbuild_path.parent.mkdir(parents=True)
            apkbuild_path.write_text(
                f"pkgname={package_origin}\npkgver=1.0.0\npkgrel=0\n"
            )
            updater_path = root / updater
            updater_path.parent.mkdir(parents=True, exist_ok=True)
            updater_path.write_text(
                """import os
from pathlib import Path

package_origin = Path(__file__).stem.removeprefix("update-")
Path("invocations.log").open("a").write(package_origin + "\\n")
updated = set(os.environ.get("UPDATED_ORIGINS", "").split(","))
failed = set(os.environ.get("FAIL_UPDATERS", "").split(","))
apkbuild = Path("packages") / package_origin / "APKBUILD"
if package_origin in updated:
    apkbuild.write_text(f"pkgname={package_origin}\\npkgver=2.0.0\\npkgrel=0\\n")
if package_origin in failed:
    raise SystemExit("intentional updater failure")
if package_origin in updated:
    print("2.0.0")
"""
            )
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "test")
        self.git(root, "config", "user.email", "test@example.com")
        self.git(root, "config", "commit.gpgsign", "false")
        self.git(root, "add", "README", "packages", "scripts")
        self.git(root, "commit", "-q", "-m", "initial")

        remote = root / "remote.git"
        self.git(root, "init", "-q", "--bare", str(remote))
        self.git(root, "remote", "add", "origin", str(remote))
        self.git(root, "push", "-q", "origin", "main")
        return root, remote

    def observe_pushes(self, remote, reject=False):
        push_log = remote.parent / "pushes.log"
        hook = remote / "hooks/pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' push >> {shlex.quote(str(push_log))}\n"
            f"exit {1 if reject else 0}\n"
        )
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        return push_log

    def run_updater(self, root, env=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            ["sh", "scripts/update-packages.sh", "packages/updaters"],
            cwd=root,
            env=merged_env,
            capture_output=True,
            text=True,
        )

    def local_history(self, root):
        return self.git(root, "log", "--format=%s").stdout.splitlines()

    def remote_history(self, remote):
        return self.remote_git(remote, "log", "main", "--format=%s").stdout.splitlines()

    def remote_file(self, remote, path):
        return self.remote_git(remote, "show", f"main:{path}").stdout

    def push_count(self, push_log):
        if not push_log.exists():
            return 0
        return len(push_log.read_text().splitlines())

    def test_no_eligible_updates_create_no_commit_or_push(self):
        root, remote = self.create_checkout()
        push_log = self.observe_pushes(remote)

        completed = self.run_updater(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.local_history(root), ["initial"])
        self.assertEqual(self.remote_history(remote), ["initial"])
        self.assertEqual(self.push_count(push_log), 0)

    def test_unregistered_package_origin_fails_before_updates_run(self):
        root, _ = self.create_checkout()
        missing = root / "packages/manual/APKBUILD"
        missing.parent.mkdir()
        missing.write_text("pkgname=manual\npkgver=1.0.0\npkgrel=0\n")

        completed = self.run_updater(root)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("manual is missing from updater manifest", completed.stderr)
        self.assertFalse((root / "invocations.log").exists())

    def test_missing_updater_fails_before_updates_run(self):
        entries = list(PACKAGE_ORIGINS)
        origin, _ = entries[0]
        entries[0] = (origin, "scripts/missing.py")
        root, _ = self.create_checkout(tuple(entries))
        (root / "scripts/missing.py").unlink()

        completed = self.run_updater(root)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(f"{origin} updater not found", completed.stderr)
        self.assertFalse((root / "invocations.log").exists())

    def test_multiple_successful_origins_make_distinct_commits_and_one_push(self):
        root, remote = self.create_checkout()
        push_log = self.observe_pushes(remote)

        completed = self.run_updater(
            root, {"UPDATED_ORIGINS": "gnupg,realm"}
        )

        expected_history = [
            "realm: upgrade to 2.0.0",
            "gnupg: upgrade to 2.0.0",
            "initial",
        ]
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.local_history(root), expected_history)
        self.assertEqual(self.remote_history(remote), expected_history)
        self.assertEqual(self.push_count(push_log), 1)

    def test_failed_updater_is_discarded_but_successful_batch_is_pushed(self):
        root, remote = self.create_checkout()
        push_log = self.observe_pushes(remote)

        completed = self.run_updater(
            root,
            {
                "UPDATED_ORIGINS": "gnupg,zerostack,realm",
                "FAIL_UPDATERS": "gnupg",
            },
        )

        expected_history = [
            "realm: upgrade to 2.0.0",
            "zerostack: upgrade to 2.0.0",
            "initial",
        ]
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(
            (root / "invocations.log").read_text().splitlines(),
            [package_origin for package_origin, _ in PACKAGE_ORIGINS],
        )
        self.assertEqual(self.local_history(root), expected_history)
        self.assertEqual(self.remote_history(remote), expected_history)
        self.assertIn("pkgver=1.0.0", self.remote_file(remote, "packages/gnupg/APKBUILD"))
        self.assertIn(
            "pkgver=2.0.0", self.remote_file(remote, "packages/zerostack/APKBUILD")
        )
        self.assertIn("pkgver=2.0.0", self.remote_file(remote, "packages/realm/APKBUILD"))
        self.assertEqual(
            self.git(root, "status", "--short", "--untracked-files=no").stdout,
            "",
        )
        self.assertEqual(self.push_count(push_log), 1)

    def test_failed_batch_push_is_attempted_once_and_keeps_local_commits(self):
        root, remote = self.create_checkout()
        push_log = self.observe_pushes(remote, reject=True)

        completed = self.run_updater(
            root, {"UPDATED_ORIGINS": "gnupg,realm"}
        )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(
            self.local_history(root),
            [
                "realm: upgrade to 2.0.0",
                "gnupg: upgrade to 2.0.0",
                "initial",
            ],
        )
        self.assertEqual(self.remote_history(remote), ["initial"])
        self.assertEqual(self.push_count(push_log), 1)


if __name__ == "__main__":
    unittest.main()
