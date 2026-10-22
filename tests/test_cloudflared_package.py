"""Contracts for the installed cloudflared package."""

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "cloudflared"
CONFIG = PACKAGE / "config.yml"
SERVICE = PACKAGE / "cloudflared.initd"


class CloudflaredPackageTest(unittest.TestCase):
    def test_go_phases_override_alpine_local_toolchain(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            go = work / "go"
            go.write_text('#!/bin/sh\nprintf "%s\\n" "${GOTOOLCHAIN-unset}"\n')
            go.chmod(0o755)
            (work / "cloudflared_man_template").touch()
            for phase in ("prepare", "build", "check"):
                with self.subTest(phase=phase):
                    result = subprocess.run(
                        [
                            "sh", "-eu", "-c",
                            '''
                            export GOTOOLCHAIN=local SOURCE_DATE_EPOCH=0 GOFLAGS=
                            PATH="$3:$PATH"
                            export PATH
                            default_prepare() { :; }
                            date() { printf '%s\\n' unused; }
                            make() { go version; }
                            envsubst() { :; }
                            . "$1"
                            "$2"
                            ''',
                            "sh", str(PACKAGE / "APKBUILD"), phase, directory,
                        ],
                        cwd=work, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "go1.27.3")

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


if __name__ == "__main__":
    unittest.main()
