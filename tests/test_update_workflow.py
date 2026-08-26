"""Package-update contract tests for .github/workflows/update.yml."""

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()
UPDATER_PATH = ROOT / "scripts" / "update-packages.sh"
UPDATER = UPDATER_PATH.read_text()
MANIFEST_PATH = ROOT / "packages" / "updaters"


def read_manifest():
    entries = []
    for line in MANIFEST_PATH.read_text().splitlines():
        if line and not line.startswith("#"):
            entries.append(tuple(line.split("|")))
    return entries


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

    def test_workflow_dispatches_one_publication_for_successful_updates(self):
        self.assertIn("GH_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("contents: write", WORKFLOW)
        self.assertIn("actions: write", WORKFLOW)
        self.assertIn("has_updates=1", UPDATER)
        self.assertIn("final_commit=$(git rev-parse origin/main)", UPDATER)
        self.assertIn("gh workflow run ci.yml --ref main", UPDATER)
        self.assertIn(
            'dispatch_publication "$initial_commit" "$final_commit"', UPDATER
        )
        self.assertIn(
            '-f base_revision="$_dp_initial_commit"', UPDATER
        )
        self.assertIn("DISPATCH_ATTEMPTS=3", UPDATER)
        self.assertIn('while [ "$_dp_attempt" -le "$DISPATCH_ATTEMPTS" ]', UPDATER)
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
