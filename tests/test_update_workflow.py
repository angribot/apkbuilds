"""Package-update contract tests for .github/workflows/update.yml."""

import pathlib
import shutil
import subprocess
import unittest

from tests.update_manifest import read_manifest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()
UPDATER_PATH = ROOT / "scripts" / "update-packages.sh"
UPDATER = UPDATER_PATH.read_text()


class PackageUpdateTest(unittest.TestCase):
    def test_workflow_uses_one_fixed_order_writer(self):
        self.assertIn("sh scripts/update-packages.sh", WORKFLOW)
        self.assertIn("fetch-depth: 0", WORKFLOW)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", WORKFLOW)
        self.assertIn("ssh-key: ${{ secrets.UPDATE_DEPLOY_KEY }}", WORKFLOW)
        self.assertNotIn("strategy:", WORKFLOW)
        self.assertNotIn("matrix:", WORKFLOW)

        self.assertIn(
            "sh scripts/update-packages.sh packages/updaters", WORKFLOW
        )
        self.assertNotIn("scripts/update-gnupg.py", UPDATER)

        entries = read_manifest()
        self.assertEqual(
            [origin for origin, _, _ in entries],
            ["gnupg", "zerostack", "tirith", "ports-box", "orbien", "realm"],
        )

    def test_manifest_registers_every_origin_updater_and_test(self):
        entries = read_manifest()
        registered = {origin for origin, _, _ in entries}
        package_origins = {
            path.parent.name for path in (ROOT / "packages").glob("*/APKBUILD")
        }
        self.assertEqual(registered, package_origins)

        for origin, updater, test in entries:
            with self.subTest(origin=origin):
                if updater == "-":
                    self.assertEqual(test, "-")
                else:
                    self.assertTrue((ROOT / updater).is_file(), updater)
                    self.assertNotEqual(test, "-")
                    self.assertTrue((ROOT / test).is_file(), test)

    def test_main_push_is_the_only_publication_trigger(self):
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("contents: write", WORKFLOW)
        self.assertNotIn("actions: write", WORKFLOW)
        self.assertNotIn("gh workflow run ci.yml", WORKFLOW)
        self.assertNotIn("gh workflow run ci.yml", UPDATER)
        self.assertNotIn("dispatch_publication", UPDATER)
        self.assertNotIn("publication_dispatch", WORKFLOW)
        self.assertNotIn("publication_dispatch", UPDATER)

    def test_workflow_stages_each_apkbuild_and_never_force_pushes(self):
        self.assertIn('git diff --quiet -- "$_pu_apkbuild"', UPDATER)
        self.assertIn('git add -- "$_pu_apkbuild"', UPDATER)
        self.assertNotIn("git add .", UPDATER)
        self.assertNotIn("git add -A", UPDATER)
        self.assertNotIn("--force", UPDATER)

    def test_workflow_retries_stale_pushes_with_a_bound(self):
        self.assertIn("PUSH_ATTEMPTS=3", UPDATER)
        self.assertIn(
            'while [ "$_pc_attempt" -le "$PUSH_ATTEMPTS" ]', UPDATER
        )
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
