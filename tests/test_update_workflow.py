"""Contract tests for the scheduled package-update workflow."""

import pathlib
import re
import shutil
import subprocess
import unittest

from tests.update_manifest import read_manifest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "update.yml"
WORKFLOW = WORKFLOW_PATH.read_text()
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
CI_WORKFLOW = CI_WORKFLOW_PATH.read_text()
UPDATER_PATH = ROOT / "scripts" / "update-packages.sh"


def child_keys(document, parent):
    """Read the immediate mapping keys under a simple workflow section."""
    lines = document.splitlines()
    parent_line = next(
        index for index, line in enumerate(lines) if line == f"{parent}:"
    )
    keys = []
    for line in lines[parent_line + 1 :]:
        if line and not line.startswith(" "):
            break
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):(?: .*)?", line)
        if match:
            keys.append(match.group(1))
    return keys


class PackageUpdateTest(unittest.TestCase):
    def test_workflow_triggers_and_permissions_are_narrow(self):
        self.assertEqual(child_keys(WORKFLOW, "on"), ["schedule"])
        self.assertEqual(child_keys(WORKFLOW, "permissions"), ["contents"])
        self.assertEqual(child_keys(CI_WORKFLOW, "on"), ["push", "pull_request"])

    def test_manifest_order_is_the_single_writer_order(self):
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

    @unittest.skipUnless(shutil.which("actionlint"), "actionlint not installed")
    def test_workflows_pass_actionlint(self):
        completed = subprocess.run(
            ["actionlint", *map(str, sorted((ROOT / ".github" / "workflows").glob("*.yml")))],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()
