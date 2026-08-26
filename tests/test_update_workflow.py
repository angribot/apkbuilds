"""Package-update contract tests for .github/workflows/update.yml."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()
UPDATER = (ROOT / "scripts" / "update-packages.sh").read_text()

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
        self.assertIn("bash scripts/update-packages.sh", WORKFLOW)
        self.assertIn("fetch-depth: 0", WORKFLOW)
        self.assertNotIn("strategy:", WORKFLOW)
        self.assertNotIn("matrix:", WORKFLOW)

        positions = []
        for package_origin, updater, apkbuild in PACKAGE_ORIGINS:
            entry = f'"{package_origin}|{updater}|{apkbuild}"'
            position = UPDATER.index(entry)
            positions.append(position)
        self.assertEqual(positions, sorted(positions))

    def test_workflow_stages_each_apkbuild_and_never_force_pushes(self):
        self.assertIn('git diff --quiet -- "$apkbuild"', UPDATER)
        self.assertIn('git add -- "$apkbuild"', UPDATER)
        self.assertNotIn("git add .", UPDATER)
        self.assertNotIn("git add -A", UPDATER)
        self.assertNotIn("--force", UPDATER)

    def test_workflow_retries_stale_pushes_with_a_bound(self):
        self.assertIn("for attempt in 1 2 3", UPDATER)
        self.assertIn("git fetch origin main", UPDATER)
        self.assertIn("git rebase origin/main", UPDATER)
        self.assertIn("git push origin HEAD:main", UPDATER)


if __name__ == "__main__":
    unittest.main()
