"""Executable POSIX-sh checks for the package smoke tests."""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SMOKE_TESTS = sorted((ROOT / "scripts").glob("test-*.sh"))


class SmokeScriptTest(unittest.TestCase):
    def test_every_smoke_script_is_an_executable_posix_shell_script(self):
        self.assertTrue(SMOKE_TESTS)
        for path in SMOKE_TESTS:
            with self.subTest(script=path.name):
                self.assertEqual(path.stat().st_mode & 0o111, 0o111)
                completed = subprocess.run(
                    ["sh", "-n", str(path)], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
