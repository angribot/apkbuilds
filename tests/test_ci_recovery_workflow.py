"""Contract tests for bounded recovery of failed main CI publications."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "ci-recovery.yml").read_text()


class CiRecoveryWorkflowTest(unittest.TestCase):
    def test_retries_failed_main_ci_runs_only_within_three_attempts(self):
        self.assertIn("workflow_run:", WORKFLOW)
        self.assertIn('workflows: ["CI"]', WORKFLOW)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", WORKFLOW)
        self.assertIn("github.event.workflow_run.run_attempt < 3", WORKFLOW)
        self.assertIn(
            "github.event.workflow_run.head_branch == github.event.repository.default_branch",
            WORKFLOW,
        )
        self.assertIn('gh run rerun "$RUN_ID" --failed', WORKFLOW)

    def test_recovery_has_only_actions_write_permission(self):
        permissions = WORKFLOW[
            WORKFLOW.index("permissions:") : WORKFLOW.index("jobs:")
        ]
        self.assertIn("actions: write", permissions)
        self.assertNotIn("contents: write", permissions)


if __name__ == "__main__":
    unittest.main()
