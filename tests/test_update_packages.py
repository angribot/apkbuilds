"""Behavior tests for the single-writer package updater."""

import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update-packages.sh"
MANIFEST = ROOT / "packages" / "updaters"


def read_manifest():
    return tuple(
        tuple(line.split("|"))
        for line in MANIFEST.read_text().splitlines()
        if line and not line.startswith("#")
    )


PACKAGE_ORIGINS = read_manifest()
UPDATER_ORIGINS = tuple(
    entry for entry in PACKAGE_ORIGINS if entry[1] != "-"
)


class UpdatePackagesTest(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
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
            "# package-origin|updater|updater-test\n"
            + "".join("|".join(entry) + "\n" for entry in entries)
        )
        (root / "README").write_text("initial\n")

        for package_origin, updater, test in entries:
            apkbuild_path = root / "packages" / package_origin / "APKBUILD"
            apkbuild_path.parent.mkdir(parents=True)
            apkbuild_path.write_text(
                f"pkgname={package_origin}\npkgver=1.0.0\npkgrel=0\n"
            )
            if updater == "-":
                continue
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
            test_path = root / test
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text("# updater behavior test registration\n")

        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "config", "user.name", "test")
        self.git(root, "config", "user.email", "test@example.com")
        self.git(root, "config", "commit.gpgsign", "false")
        self.git(root, "add", "README", "packages", "scripts", "tests")
        self.git(root, "commit", "-q", "-m", "initial")

        remote = root / "remote.git"
        self.git(root, "init", "-q", "--bare", str(remote))
        self.git(root, "remote", "add", "origin", str(remote))
        self.git(root, "push", "-q", "origin", "main")
        return root, remote

    def install_fake_gh(self, root):
        fake_bin = root / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        invocations = root / "gh-invocations"
        gh = fake_bin / "gh"
        gh.write_text(
            """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_INVOCATIONS"
count=0
if [ -e "$GH_ATTEMPTS" ]; then
    count=$(cat "$GH_ATTEMPTS")
fi
count=$((count + 1))
printf '%s\\n' "$count" > "$GH_ATTEMPTS"
if [ "$count" -le "${GH_FAIL_FIRST:-0}" ]; then
    exit 1
fi
if [ "${GH_EXIT:-0}" -ne 0 ]; then
    exit "$GH_EXIT"
fi
"""
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        return {
            "PATH": os.pathsep.join([str(fake_bin), os.environ["PATH"]]),
            "GH_INVOCATIONS": str(invocations),
            "GH_ATTEMPTS": str(root / "gh-attempts"),
        }

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

    def remote_file(self, root, path):
        return self.git(root, "show", f"origin/main:{path}").stdout

    def test_no_eligible_updates_create_no_commit(self):
        root, _ = self.create_checkout()
        env = self.install_fake_gh(root)

        completed = self.run_updater(root, env)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.git(root, "log", "origin/main", "--format=%s").stdout.splitlines(),
            ["initial"],
        )
        self.assertFalse((root / "gh-invocations").exists())

    def test_origin_without_updater_is_explicitly_skipped(self):
        entries = (*PACKAGE_ORIGINS, ("manual", "-", "-"))
        root, _ = self.create_checkout(entries)

        completed = self.run_updater(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("manual has no updater; skipping", completed.stdout)
        self.assertEqual(
            (root / "invocations.log").read_text().splitlines(),
            [origin for origin, _, _ in UPDATER_ORIGINS],
        )

    def test_unregistered_package_origin_fails_before_updates_run(self):
        root, _ = self.create_checkout()
        missing = root / "packages/manual/APKBUILD"
        missing.parent.mkdir()
        missing.write_text("pkgname=manual\npkgver=1.0.0\npkgrel=0\n")

        completed = self.run_updater(root)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("manual is missing from updater manifest", completed.stderr)
        self.assertFalse((root / "invocations.log").exists())

    def test_updater_without_test_registration_fails_before_updates_run(self):
        entries = list(PACKAGE_ORIGINS)
        origin, updater, _ = entries[0]
        entries[0] = (origin, updater, "-")
        root, _ = self.create_checkout(tuple(entries))

        completed = self.run_updater(root)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            f"{origin} updater has no test registration", completed.stderr
        )
        self.assertFalse((root / "invocations.log").exists())

    def test_failed_package_origin_does_not_block_or_leak_into_later_origins(self):
        root, _ = self.create_checkout()
        initial_commit = self.git(root, "rev-parse", "HEAD").stdout.strip()
        env = self.install_fake_gh(root)
        env.update({"UPDATED_ORIGINS": "zerostack,realm", "FAIL_UPDATERS": "gnupg"})

        completed = self.run_updater(root, env)

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(
            (root / "invocations.log").read_text().splitlines(),
            [package_origin for package_origin, _, _ in UPDATER_ORIGINS],
        )
        self.assertIn("pkgver=1.0.0", self.remote_file(root, "packages/gnupg/APKBUILD"))
        self.assertIn(
            "pkgver=2.0.0", self.remote_file(root, "packages/zerostack/APKBUILD")
        )
        self.assertIn("pkgver=2.0.0", self.remote_file(root, "packages/realm/APKBUILD"))
        self.assertEqual(
            self.git(root, "status", "--short", "--untracked-files=no").stdout,
            "",
        )
        final_commit = self.git(root, "rev-parse", "origin/main").stdout.strip()
        self.assertEqual(
            (root / "gh-invocations").read_text().splitlines(),
            [
                "workflow run ci.yml --ref main "
                f"-f base_revision={initial_commit} "
                f"-f revision={final_commit} -f full=false"
            ],
        )

    def test_successful_updates_dispatch_once_for_final_revision(self):
        root, _ = self.create_checkout()
        initial_commit = self.git(root, "rev-parse", "HEAD").stdout.strip()
        env = self.install_fake_gh(root)
        env["UPDATED_ORIGINS"] = "gnupg,realm"

        completed = self.run_updater(root, env)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        invocations = (root / "gh-invocations").read_text().splitlines()
        self.assertEqual(len(invocations), 1)
        final_commit = self.git(root, "rev-parse", "origin/main").stdout.strip()
        self.assertEqual(
            invocations[0],
            "workflow run ci.yml --ref main "
            f"-f base_revision={initial_commit} "
            f"-f revision={final_commit} -f full=false",
        )

    def test_exhausted_push_retries_abandon_only_current_package_origin(self):
        root, _ = self.create_checkout()
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        push_count = root / "push-count"
        real_git = shutil.which("git")
        wrapper = fake_bin / "git"
        wrapper.write_text(
            """#!/bin/sh
if [ "${1:-}" = push ]; then
    count=0
    if [ -e "$PUSH_COUNT_FILE" ]; then
        count=$(cat "$PUSH_COUNT_FILE")
    fi
    count=$((count + 1))
    echo "$count" > "$PUSH_COUNT_FILE"
    if [ "$count" -le 3 ]; then
        exit 1
    fi
fi
exec "$REAL_GIT" "$@"
"""
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        path = os.pathsep.join([str(fake_bin), os.environ["PATH"]])

        completed = self.run_updater(
            root,
            {
                "UPDATED_ORIGINS": "gnupg,zerostack,realm",
                "PATH": path,
                "REAL_GIT": real_git,
                "PUSH_COUNT_FILE": str(push_count),
            },
        )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(
            (root / "invocations.log").read_text().splitlines(),
            [package_origin for package_origin, _, _ in UPDATER_ORIGINS],
        )
        self.assertIn("pkgver=1.0.0", self.remote_file(root, "packages/gnupg/APKBUILD"))
        self.assertIn(
            "pkgver=2.0.0", self.remote_file(root, "packages/zerostack/APKBUILD")
        )
        self.assertIn("pkgver=2.0.0", self.remote_file(root, "packages/realm/APKBUILD"))
        self.assertIn("gnupg push failed after 3 attempts", completed.stderr)

    def test_dispatch_retries_after_a_transient_failure(self):
        root, _ = self.create_checkout()
        env = self.install_fake_gh(root)
        env.update({"UPDATED_ORIGINS": "gnupg", "GH_FAIL_FIRST": "2"})

        completed = self.run_updater(root, env)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len((root / "gh-invocations").read_text().splitlines()), 3)

    def test_dispatch_failure_is_visible_after_a_successful_update(self):
        root, _ = self.create_checkout()
        env = self.install_fake_gh(root)
        env.update({"UPDATED_ORIGINS": "gnupg", "GH_EXIT": "1"})

        completed = self.run_updater(root, env)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("could not dispatch CI publication", completed.stderr)
        self.assertIn("3 attempts", completed.stderr)
        self.assertEqual(len((root / "gh-invocations").read_text().splitlines()), 3)
        self.assertIn("pkgver=2.0.0", self.remote_file(root, "packages/gnupg/APKBUILD"))

    def test_stale_main_is_rebased_and_pushed_without_force(self):
        root, remote = self.create_checkout()
        gh_env = self.install_fake_gh(root)
        race_clone = root / "race"
        self.git(root, "clone", "-q", "-b", "main", str(remote), str(race_clone))
        self.git(race_clone, "config", "user.name", "racer")
        self.git(race_clone, "config", "user.email", "racer@example.com")
        self.git(race_clone, "config", "commit.gpgsign", "false")
        (race_clone / "README").write_text("concurrent change\n")
        self.git(race_clone, "add", "README")
        self.git(race_clone, "commit", "-q", "-m", "concurrent change")

        fake_bin = root / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        marker = root / "race.marker"
        real_git = shutil.which("git")
        wrapper = fake_bin / "git"
        wrapper.write_text(
            """#!/bin/sh
if [ "$1" = push ] && [ ! -e "$RACE_MARKER" ]; then
    : > "$RACE_MARKER"
    "$REAL_GIT" -C "$RACE_CLONE" push -q origin HEAD:main
fi
exec "$REAL_GIT" "$@"
"""
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        path = os.pathsep.join([str(fake_bin), os.environ["PATH"]])

        completed = self.run_updater(
            root,
            {
                **gh_env,
                "UPDATED_ORIGINS": "gnupg",
                "PATH": path,
                "REAL_GIT": real_git,
                "RACE_CLONE": str(race_clone),
                "RACE_MARKER": str(marker),
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.remote_file(root, "README"), "concurrent change\n")
        self.assertIn("pkgver=2.0.0", self.remote_file(root, "packages/gnupg/APKBUILD"))
        self.assertIn("rebasing onto origin/main", completed.stdout)


if __name__ == "__main__":
    unittest.main()
