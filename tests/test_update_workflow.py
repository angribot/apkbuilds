"""Package-update contract tests for .github/workflows/update.yml."""

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()
UPDATER_PATH = ROOT / "scripts" / "update-packages.sh"
UPDATER = UPDATER_PATH.read_text()

PACKAGE_ORIGINS = (
    ("gnupg", "scripts/update-gnupg.py", "packages/gnupg/APKBUILD"),
    ("zerostack", "scripts/update-zerostack.py", "packages/zerostack/APKBUILD"),
    ("tirith", "scripts/update-tirith.py", "packages/tirith/APKBUILD"),
    ("ports-box", "scripts/update-ports-box.py", "packages/ports-box/APKBUILD"),
    ("orbien", "scripts/update-orbien.py", "packages/orbien/APKBUILD"),
    ("realm", "scripts/update-realm.py", "packages/realm/APKBUILD"),
)


class PackageUpdateTest(unittest.TestCase):
    def test_workflow_uses_one_fixed_order_writer(self):
        self.assertIn("sh scripts/update-packages.sh", WORKFLOW)
        self.assertIn("fetch-depth: 0", WORKFLOW)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", WORKFLOW)
        self.assertNotIn("strategy:", WORKFLOW)
        self.assertNotIn("matrix:", WORKFLOW)

        positions = []
        for package_origin, updater, apkbuild in PACKAGE_ORIGINS:
            entry = f"{package_origin}|{updater}|{apkbuild}"
            position = UPDATER.index(entry)
            positions.append(position)
        self.assertEqual(positions, sorted(positions))

    def test_workflow_dispatches_one_publication_for_successful_updates(self):
        self.assertIn("GH_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("contents: write", WORKFLOW)
        self.assertIn("actions: write", WORKFLOW)
        self.assertIn("has_updates=1", UPDATER)
        self.assertIn("final_commit=$(git rev-parse origin/main)", UPDATER)
        self.assertIn("gh workflow run ci.yml --ref main", UPDATER)
        self.assertIn(
            '-f base_revision="$initial_commit" -f revision="$final_commit"',
            UPDATER,
        )
        self.assertIn("could not dispatch CI publication", UPDATER)

    def test_workflow_stages_each_apkbuild_and_never_force_pushes(self):
        self.assertIn('git diff --quiet -- "$_pu_apkbuild"', UPDATER)
        self.assertIn('git add -- "$_pu_apkbuild"', UPDATER)
        self.assertNotIn("git add .", UPDATER)
        self.assertNotIn("git add -A", UPDATER)
        self.assertNotIn("--force", UPDATER)

    def test_workflow_retries_stale_pushes_with_a_bound(self):
        self.assertIn("for _pc_attempt in 1 2 3", UPDATER)
        self.assertIn("git fetch origin main", UPDATER)
        self.assertIn("git rebase origin/main", UPDATER)
        self.assertIn("git push origin HEAD:main", UPDATER)

    def test_updater_is_posix_sh_clean(self):
        completed = subprocess.run(
            ["sh", "-n", str(UPDATER_PATH)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_updater_passes_posix_shellcheck(self):
        completed = subprocess.run(
            ["shellcheck", "--shell=sh", str(UPDATER_PATH)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()
