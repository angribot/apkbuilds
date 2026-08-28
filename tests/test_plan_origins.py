"""Behavior tests for the CI repository-reconciliation planning seam."""

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
    def git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
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
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.commit("initial", "packages")
        self.initial = self.revision()

        self.write_apkbuild("alpha", "2.0.0")
        self.commit("update alpha", "packages/alpha/APKBUILD")
        self.alpha_commit = self.revision()

        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text(
            "name: fixed CI\n"
        )
        self.commit("fix CI", ".github/workflows/ci.yml")
        self.ci_fix_commit = self.revision()

        self.write_apkbuild("beta", "2.0.0")
        self.commit("update beta", "packages/beta/APKBUILD")
        self.beta_commit = self.revision()

        (self.root / "packages" / "alpha" / "fix.patch").write_text(
            "updated packaging input\n"
        )
        self.commit("change alpha patch", "packages/alpha/fix.patch")
        self.auxiliary_commit = self.revision()

        self.git(
            "mv",
            "packages/alpha/fix.patch",
            "packages/beta/fix.patch",
        )
        self.git("commit", "-q", "-m", "move package input")
        self.move_commit = self.revision()

    def revision(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def write_apkbuild(self, origin, version, arch=None):
        architecture = "" if arch is None else f'arch="{arch}"\n'
        (self.root / "packages" / origin / "APKBUILD").write_text(
            f"pkgname={origin}\npkgver={version}\npkgrel=0\n{architecture}"
        )

    def commit(self, message, path):
        self.git("add", path)
        self.git("commit", "-q", "-m", message)

    def run_plan(self, *, event, revision, base="", before=""):
        self.git("switch", "-q", "--detach", revision)
        output = self.root / "output"
        runner_temp = self.root / "runner-temp"
        runner_temp.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "EVENT": event,
                "BASE": base,
                "BEFORE": before,
                "REVISION": revision,
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

    def matrix_entries(self, completed):
        return json.loads(self.plan_outputs(completed)["matrix"])["include"]

    def test_main_push_reconciles_every_supported_declared_build(self):
        completed = self.run_plan(
            event="push",
            revision=self.beta_commit,
            before=self.ci_fix_commit,
        )

        entries = self.matrix_entries(completed)
        self.assertEqual(
            {(item["origin"], item["arch"]) for item in entries},
            {
                ("alpha", "x86_64"),
                ("alpha", "aarch64"),
                ("beta", "x86_64"),
                ("beta", "aarch64"),
            },
        )

    def test_ci_only_main_fix_reconsiders_an_earlier_unpublished_origin(self):
        completed = self.run_plan(
            event="push",
            revision=self.ci_fix_commit,
            before=self.alpha_commit,
        )

        entries = self.matrix_entries(completed)
        self.assertEqual(
            {item["origin"] for item in entries},
            {"alpha", "beta"},
        )

    def test_pull_request_selects_only_changed_package_origins(self):
        completed = self.run_plan(
            event="pull_request",
            revision=self.alpha_commit,
            base=self.initial,
        )

        entries = self.matrix_entries(completed)
        self.assertEqual(
            {(item["origin"], item["arch"]) for item in entries},
            {("alpha", "x86_64"), ("alpha", "aarch64")},
        )

    def test_automation_only_pull_request_is_a_visible_no_op(self):
        completed = self.run_plan(
            event="pull_request",
            revision=self.ci_fix_commit,
            base=self.alpha_commit,
        )

        outputs = self.plan_outputs(completed)
        self.assertEqual(outputs["has_origins"], "false")
        self.assertEqual(json.loads(outputs["matrix"]), {"include": []})

    def test_auxiliary_package_input_selects_its_origin(self):
        completed = self.run_plan(
            event="pull_request",
            revision=self.auxiliary_commit,
            base=self.beta_commit,
        )

        entries = self.matrix_entries(completed)
        self.assertEqual(
            {item["origin"] for item in entries},
            {"alpha"},
        )

    def test_moved_package_input_selects_both_origins(self):
        completed = self.run_plan(
            event="pull_request",
            revision=self.move_commit,
            base=self.auxiliary_commit,
        )

        entries = self.matrix_entries(completed)
        self.assertEqual(
            {item["origin"] for item in entries},
            {"alpha", "beta"},
        )

    def test_removing_a_package_origin_fails_explicitly(self):
        self.git("switch", "-q", "main")
        parent = self.revision()
        self.git("rm", "-q", "-r", "packages/alpha")
        self.git("commit", "-q", "-m", "remove alpha")
        removed = self.revision()

        completed = self.run_plan(
            event="push",
            revision=removed,
            before=parent,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("removing package origin alpha is unsupported", completed.stderr)
        self.assertFalse((self.root / "output").exists())

    def test_narrowing_origin_architectures_fails_explicitly(self):
        self.git("switch", "-q", "main")
        parent = self.revision()
        self.write_apkbuild("alpha", "3.0.0", "x86_64")
        self.commit("drop alpha aarch64", "packages/alpha/APKBUILD")
        narrowed = self.revision()

        completed = self.run_plan(
            event="push",
            revision=narrowed,
            before=parent,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            "removing architecture aarch64 from package origin alpha is unsupported",
            completed.stderr,
        )
        self.assertFalse((self.root / "output").exists())

    def test_planner_has_no_manual_reconciliation_mode(self):
        completed = self.run_plan(
            event="push",
            revision=self.ci_fix_commit,
            before=self.alpha_commit,
        )

        self.assertNotIn("reconcile", self.plan_outputs(completed))


if __name__ == "__main__":
    unittest.main()
