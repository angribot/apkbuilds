"""Contracts for the installed Orbien package family."""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVICE = ROOT / "packages" / "orbien" / "orbien-server.initd"
SMOKE_TEST = ROOT / "scripts" / "test-orbien.sh"


class OrbienPackageTest(unittest.TestCase):
    def test_service_rejects_missing_operator_configuration(self):
        result = subprocess.run(
            [
                "sh",
                "-c",
                'eerror() { printf "%s\\n" "$*" >&2; }; . "$1"; start_pre',
                "sh",
                str(SERVICE),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/etc/orbien/orbien-server.toml not found", result.stderr)

    def test_package_smoke_test_covers_installed_contract(self):
        self.assertTrue(SMOKE_TEST.is_file())
        self.assertEqual(SMOKE_TEST.stat().st_mode & 0o111, 0o111)


if __name__ == "__main__":
    unittest.main()
