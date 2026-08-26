"""Contract tests for the manual cold/warm Rust cache benchmark."""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "ci-cache-benchmark.yml").read_text()
BUILD = (ROOT / "scripts" / "build-package-family.sh").read_text()


class CiCacheBenchmarkTest(unittest.TestCase):
    def test_benchmark_builds_a_rust_origin_twice_with_shared_caches(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("ORIGIN: orbien", WORKFLOW)
        self.assertEqual(WORKFLOW.count("build-package-family.sh"), 1)
        self.assertIn("for mode in cold warm", WORKFLOW)
        self.assertIn("printf 'build_mode=%s\\n' \"$mode\"", WORKFLOW)
        self.assertIn('echo "### Orbien $mode compiler-cache measurement"', WORKFLOW)
        self.assertIn("--force-build", WORKFLOW)
        self.assertIn("/home/builder/.cache/cargo", WORKFLOW)
        self.assertIn("/home/builder/.cache/sccache", WORKFLOW)
        self.assertIn("--force-build", BUILD)

    def test_benchmark_does_not_grant_publication_permissions(self):
        permissions = WORKFLOW[
            WORKFLOW.index("permissions:") : WORKFLOW.index("jobs:")
        ]
        self.assertIn("contents: read", permissions)
        self.assertNotIn("contents: write", permissions)
        self.assertNotIn("PAGES_DEPLOY_KEY", WORKFLOW)

    def test_build_module_remains_posix_sh_clean(self):
        completed = subprocess.run(
            ["sh", "-n", str(ROOT / "scripts" / "build-package-family.sh")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
