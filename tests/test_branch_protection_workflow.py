"""Contract tests for the source-controlled branch protection verifier."""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "verify-branch-protection.yml").read_text()
SCRIPT_PATH = ROOT / "scripts" / "verify-branch-rulesets.sh"
SCRIPT = SCRIPT_PATH.read_text()


class BranchProtectionTest(unittest.TestCase):
    def test_workflow_runs_the_verifier_on_schedule_and_by_dispatch(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("schedule:", WORKFLOW)
        self.assertIn("verify-branch-rulesets.sh", WORKFLOW)
        self.assertIn("GH_TOKEN: ${{ github.token }}", WORKFLOW)
        self.assertIn("GITHUB_REPOSITORY: ${{ github.repository }}", WORKFLOW)

    def test_verifier_checks_both_active_rulesets(self):
        self.assertIn('Protect main write path', SCRIPT)
        self.assertIn('Protect gh-pages write path', SCRIPT)
        self.assertIn('refs/heads/main', SCRIPT)
        self.assertIn('refs/heads/gh-pages', SCRIPT)
        self.assertIn('include == [$ref]', SCRIPT)
        self.assertIn('exclude == []', SCRIPT)
        self.assertIn('CI / gate', SCRIPT)
        self.assertIn('required_approving_review_count', SCRIPT)
        self.assertIn('non_fast_forward', SCRIPT)
        self.assertIn('DeployKey', SCRIPT)
        self.assertIn('bypass_actors[]?] | length == 1', SCRIPT)
        self.assertIn('bypass_mode == "always"', SCRIPT)

    def test_verifier_is_posix_sh_clean(self):
        completed = subprocess.run(
            ["sh", "-n", str(SCRIPT_PATH)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_workflow_does_not_grant_write_permissions(self):
        permissions = WORKFLOW[
            WORKFLOW.index("permissions:") : WORKFLOW.index("jobs:")
        ]
        self.assertIn("contents: read", permissions)
        self.assertNotIn("contents: write", permissions)
        self.assertNotIn("actions: write", permissions)


if __name__ == "__main__":
    unittest.main()
