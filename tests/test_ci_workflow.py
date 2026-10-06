"""Contract tests for the CI publication job graph."""

import os
import pathlib
import re
import subprocess
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
CI_WORKFLOW = CI_WORKFLOW_PATH.read_text()


def job_blocks(document):
    """Return each job's block in a workflow document, keyed by job name."""
    jobs = document.split("\njobs:\n", 1)[1]
    headers = list(re.finditer(r"^  ([a-z][a-z0-9-]*):$", jobs, re.MULTILINE))
    return {
        header.group(1): jobs[
            header.start() : (
                headers[index + 1].start()
                if index + 1 < len(headers)
                else len(jobs)
            )
        ]
        for index, header in enumerate(headers)
    }


def job_value(block, key):
    """Return a job-level key's inline value, or None when it is absent."""
    match = re.search(rf"^    {re.escape(key)}: (.*)$", block, re.MULTILINE)
    return match.group(1) if match is not None else None


def job_needs(block):
    value = job_value(block, "needs")
    if value is None:
        return set()
    if value.startswith("["):
        return set(value.strip("[]").split(", "))
    return {value}


def job_lines(block):
    return [line.strip() for line in block.splitlines() if line.strip()]


class PublicationJobGraphTest(unittest.TestCase):
    def setUp(self):
        self.jobs = job_blocks(CI_WORKFLOW)

    def test_build_runs_only_for_planned_origins_with_the_planner_matrix(self):
        build = self.jobs["build"]
        lines = job_lines(build)

        self.assertEqual({"check"}, job_needs(build))
        self.assertEqual(
            "needs.check.outputs.has_origins == 'true'", job_value(build, "if")
        )
        self.assertIn("matrix: ${{ fromJSON(needs.check.outputs.matrix) }}", lines)
        self.assertIn(
            "name: built-${{ matrix.arch }}-${{ matrix.origin }}", lines
        )

    def test_sign_is_default_branch_only_and_uses_the_release_environment(self):
        sign = self.jobs["sign"]
        lines = job_lines(sign)

        self.assertEqual({"build", "check"}, job_needs(sign))
        self.assertEqual(
            "github.ref_name == github.event.repository.default_branch",
            job_value(sign, "if"),
        )
        self.assertEqual("release", job_value(sign, "environment"))
        self.assertIn("ABUILD_PRIVATE_KEY: ${{ secrets.ABUILD_PRIVATE_KEY }}", lines)
        self.assertIn("pattern: built-*", lines)
        self.assertIn("name: signed-repository", lines)
        self.assertIn("include-hidden-files: true", lines)

    def test_verify_gates_on_the_created_snapshot(self):
        verify = self.jobs["verify"]

        self.assertEqual({"sign"}, job_needs(verify))
        self.assertEqual(
            "needs.sign.outputs.snapshot_created == 'true'",
            job_value(verify, "if"),
        )
        self.assertIn("name: signed-repository", job_lines(verify))

    def test_integration_uses_both_native_architectures_without_release_secrets(self):
        integration = self.jobs["integration"]
        self.assertEqual({"check"}, job_needs(integration))
        self.assertEqual(
            "needs.check.outputs.run_integration == 'true'", job_value(integration, "if")
        )
        for line in (
            "- arch: x86_64", "runner: ubuntu-24.04",
            "- arch: aarch64", "runner: ubuntu-24.04-arm",
            "python3 tests/integration/run.py", "persist-credentials: false",
        ):
            self.assertIn(line, job_lines(integration))
        self.assertNotIn("secrets.", integration)
        self.assertIsNone(job_value(integration, "environment"))

    def test_ci_waits_for_every_dynamic_job(self):
        self.assertEqual(
            {"check", "integration", "build", "sign", "verify"}, job_needs(self.jobs["ci"])
        )

    def test_required_ci_gate_enforces_selected_integration_results(self):
        script = textwrap.dedent(self.jobs["ci"].split("        run: |\n", 1)[1])
        for event in ("pull_request", "push"):
            for selected, result, expected in (
                ("false", "skipped", 0),
                ("true", "success", 0),
                ("true", "failure", 1),
                ("true", "cancelled", 1),
                ("true", "skipped", 1),
            ):
                with self.subTest(event=event, selected=selected, result=result):
                    completed = subprocess.run(
                        ["sh", "-c", script], capture_output=True, text=True,
                        env={
                            **os.environ, "EVENT": event, "CHECK": "success",
                            "HAS_ORIGINS": "false", "BUILD": "skipped",
                            "SIGN": "skipped", "VERIFY": "skipped",
                            "SNAPSHOT_CREATED": "false", "RUN_INTEGRATION": selected,
                            "INTEGRATION": result,
                        },
                    )
                    self.assertEqual(completed.returncode, expected, completed.stderr)

    def test_publication_completion_rejects_an_unpublished_snapshot(self):
        completion = self.jobs["publication"]
        self.assertEqual({"ci", "sign", "publish"}, job_needs(completion))
        self.assertEqual("always()", job_value(completion, "if"))
        script = textwrap.dedent(completion.split("        run: |\n", 1)[1])
        for event, ci, sign, snapshot, publish, expected in (
            ("push", "success", "success", "true", "success", 0),
            ("push", "success", "success", "true", "skipped", 1),
            ("push", "success", "success", "true", "failure", 1),
            ("push", "success", "success", "true", "cancelled", 1),
            ("push", "success", "success", "false", "skipped", 0),
            ("push", "failure", "skipped", "", "skipped", 1),
            ("push", "success", "failure", "", "skipped", 1),
            ("pull_request", "success", "skipped", "", "skipped", 0),
            ("pull_request", "failure", "skipped", "", "skipped", 1),
        ):
            with self.subTest(event=event, snapshot=snapshot, publish=publish, ci=ci, sign=sign):
                completed = subprocess.run(
                    ["sh", "-c", script], capture_output=True, text=True,
                    env={
                        **os.environ, "EVENT": event, "CI": ci, "SIGN": sign,
                        "SNAPSHOT_CREATED": snapshot, "PUBLISH": publish,
                    },
                )
                self.assertEqual(completed.returncode, expected, completed.stderr)

    def test_publish_requires_the_default_branch_and_every_prior_success(self):
        publish = self.jobs["publish"]
        lines = job_lines(publish)

        self.assertEqual({"ci", "sign", "verify"}, job_needs(publish))
        self.assertIn("!cancelled() &&", lines)
        for condition in (
            "github.ref_name == github.event.repository.default_branch &&",
            "needs.ci.result == 'success' && needs.sign.result == 'success' &&",
            "needs.sign.outputs.snapshot_created == 'true' &&",
            "needs.verify.result == 'success'",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, lines)
        self.assertIn("PAGES_DEPLOY_KEY: ${{ secrets.PAGES_DEPLOY_KEY }}", lines)


if __name__ == "__main__":
    unittest.main()
