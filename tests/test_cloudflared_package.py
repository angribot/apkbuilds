"""Contracts for the installed cloudflared package."""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "cloudflared"
CONFIG = PACKAGE / "config.yml"
SERVICE = PACKAGE / "cloudflared.initd"
SMOKE_TEST = ROOT / "scripts" / "test-cloudflared.sh"


class CloudflaredPackageTest(unittest.TestCase):
    def test_shipped_configuration_is_non_live(self):
        active_lines = [
            line.strip()
            for line in CONFIG.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(active_lines, [])
        text = CONFIG.read_text()
        self.assertIn("credentials-file:", text)
        self.assertIn("token-file:", text)

    def test_service_rejects_missing_configuration(self):
        result = subprocess.run(
            ["sh", "-c", 'eerror() { printf "%s\\n" "$*" >&2; }; . "$1"; start_pre', "sh", str(SERVICE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configuration /etc/cloudflared/config.yml not found", result.stderr)

    def test_package_smoke_test_covers_installed_contract(self):
        self.assertTrue(SMOKE_TEST.is_file())
        self.assertEqual(SMOKE_TEST.stat().st_mode & 0o111, 0o111)


if __name__ == "__main__":
    unittest.main()
