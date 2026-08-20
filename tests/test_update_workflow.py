"""Package-update contract tests for .github/workflows/update.yml."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()


class PackageUpdateTest(unittest.TestCase):
    def test_daily_workflow_runs_orbien_updater_and_stages_only_its_apkbuild(self):
        self.assertIn(
            "- package: orbien\n            updater: scripts/update-orbien.py",
            WORKFLOW,
        )
        self.assertIn("apkbuild: packages/orbien/APKBUILD", WORKFLOW)
        self.assertIn('git diff --quiet -- "$APKBUILD"', WORKFLOW)
        self.assertIn('git add "$APKBUILD"', WORKFLOW)
        self.assertNotIn("git add .", WORKFLOW)
        self.assertNotIn("git add -A", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
