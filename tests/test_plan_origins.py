"""Behavior tests for the CI package-origin planning seam."""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "scripts" / "plan-origins.sh"


class PlanOriginsTest(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        (self.root / "scripts").mkdir()
        (self.root / "packages" / "alpha").mkdir(parents=True)
        (self.root / "packages" / "beta").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "lib.sh", self.root / "scripts/lib.sh")

        for origin in ("alpha", "beta"):
            self.write_apkbuild(origin, "1.0.0")
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "config", "user.name", "test")
        self.git(self.root, "config", "user.email", "test@example.com")
        self.git(self.root, "config", "commit.gpgsign", "false")
        self.commit("initial", "packages")
        self.initial = self.git(self.root, "rev-parse", "HEAD").stdout.strip()

        self.write_apkbuild("alpha", "2.0.0")
        self.commit("update alpha", "packages/alpha/APKBUILD")
        self.alpha_commit = self.git(self.root, "rev-parse", "HEAD").stdout.strip()

        self.write_apkbuild("beta", "2.0.0")
        self.commit("update beta", "packages/beta/APKBUILD")
        self.beta_commit = self.git(self.root, "rev-parse", "HEAD").stdout.strip()

        self.git(self.root, "switch", "-q", "-c", "feature", self.initial)
        self.write_apkbuild("alpha", "3.0.0")
        self.commit("feature alpha", "packages/alpha/APKBUILD")
        self.feature_commit = self.git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.git(self.root, "switch", "-q", "main")

    def write_apkbuild(self, origin, version):
        (self.root / "packages" / origin / "APKBUILD").write_text(
            f"pkgname={origin}\npkgver={version}\npkgrel=0\n"
        )

    def commit(self, message, path):
        self.git(self.root, "add", path)
        self.git(self.root, "commit", "-q", "-m", message)

    def run_plan(self, *, revision, base_revision="", full="false"):
        output = self.root / "output"
        runner_temp = self.root / "runner-temp"
        runner_temp.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "EVENT": "workflow_dispatch",
                "FULL": full,
                "BASE": "",
                "BEFORE": "",
                "REVISION": revision,
                "BASE_REVISION": base_revision,
                "MAIN_REVISION": "main",
                "RUNNER_TEMP": str(runner_temp),
                "GITHUB_OUTPUT": str(output),
            }
        )
        return subprocess.run(
            ["sh", str(PLAN)],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
        )

    def plan_outputs(self, completed):
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = self.root / "output"
        return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_manual_dispatch_spans_all_updates_since_explicit_base(self):
        completed = self.run_plan(
            revision=self.beta_commit,
            base_revision=self.initial,
        )

        outputs = self.plan_outputs(completed)
        matrix = json.loads(outputs["matrix"])
        self.assertEqual(
            {item["origin"] for item in matrix["include"]}, {"alpha", "beta"}
        )
        self.assertEqual(outputs["has_origins"], "true")

    def test_manual_dispatch_defaults_to_selected_revision_parent(self):
        completed = self.run_plan(revision=self.beta_commit)

        outputs = self.plan_outputs(completed)
        matrix = json.loads(outputs["matrix"])
        self.assertEqual({item["origin"] for item in matrix["include"]}, {"beta"})

    def test_full_manual_dispatch_plans_every_origin(self):
        completed = self.run_plan(revision=self.beta_commit, full="true")

        outputs = self.plan_outputs(completed)
        matrix = json.loads(outputs["matrix"])
        self.assertEqual(
            {item["origin"] for item in matrix["include"]}, {"alpha", "beta"}
        )

    def test_no_changed_origins_is_a_visible_no_op(self):
        completed = self.run_plan(
            revision=self.initial,
            base_revision=self.initial,
        )

        outputs = self.plan_outputs(completed)
        self.assertEqual(outputs["has_origins"], "false")
        self.assertEqual(json.loads(outputs["matrix"]), {"include": []})

    def test_off_main_revision_fails_loudly(self):
        completed = self.run_plan(
            revision=self.feature_commit,
            base_revision=self.initial,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not on main", completed.stderr)

    def test_unrelated_or_reversed_revisions_fail_loudly(self):
        completed = self.run_plan(
            revision=self.alpha_commit,
            base_revision=self.beta_commit,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not an ancestor", completed.stderr)


if __name__ == "__main__":
    unittest.main()
