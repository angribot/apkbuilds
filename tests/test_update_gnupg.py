import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "update_gnupg", SCRIPTS / "update-gnupg.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)

FAKE_GPG = """\
#!/usr/bin/env python3
import os
import sys

log = os.environ.get("FAKE_GPG_LOG")
if log:
    with open(log, "a") as handle:
        handle.write(" ".join(sys.argv[1:]) + "\\n")
if "--import" in sys.argv[1:]:
    raise SystemExit(0)
status = os.environ.get("FAKE_GPG_STATUS", "")
if status:
    sys.stdout.write(status)
raise SystemExit(int(os.environ.get("FAKE_GPG_EXIT", "0")))
"""

PINNED_FINGERPRINT = "6DAA6E64A76D2840571B4902528897B826403ADA"
UNPINNED_FINGERPRINT = "1234567890ABCDEF1234567890ABCDEF12345678"


def validsig(fingerprint):
    return (
        f"[GNUPG:] VALIDSIG {fingerprint} 2026-01-01 1767225600 0 4 0 1 10 00 "
        f"{fingerprint}\n"
    )


class UpdateGnupgTest(unittest.TestCase):
    def test_newest_eligible_version_ignores_ineligible_files(self):
        index = '<a href="gnupg-2.5.9.tar.bz2">x</a><a href="gnupg-2.5.10.tar.bz2">x</a><a href="gnupg-2.6.0-beta.tar.bz2">x</a>'
        self.assertEqual(update.newest_eligible_version(index), "2.5.10")

    def test_update_resets_revision_and_checksum(self):
        text = "pkgver=2.4.9\npkgrel=3\n" + "a" * 128 + "  gnupg-2.4.9.tar.bz2\n"
        result = update.updated_apkbuild(text, "2.5.21", "b" * 128)
        self.assertIn("pkgver=2.5.21\npkgrel=0", result)
        self.assertIn("b" * 128 + "  gnupg-2.5.21.tar.bz2", result)

    def test_update_rejects_missing_checksum(self):
        with self.assertRaisesRegex(ValueError, "source checksum"):
            update.updated_apkbuild("pkgver=2.4.9\npkgrel=0\n", "2.5.21", "b" * 128)


class VerifySignerTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        fake_bin = Path(directory.name) / "bin"
        fake_bin.mkdir()
        gpg = fake_bin / "gpg"
        gpg.write_text(FAKE_GPG)
        gpg.chmod(gpg.stat().st_mode | stat.S_IXUSR)
        self.log = Path(directory.name) / "gpg.log"
        self.env = {
            "PATH": os.pathsep.join([str(fake_bin), os.environ["PATH"]]),
            "FAKE_GPG_LOG": str(self.log),
        }

    def verify_with_gpg(self, status="", exit_code=0):
        self.env["FAKE_GPG_STATUS"] = status
        self.env["FAKE_GPG_EXIT"] = str(exit_code)
        with mock.patch.dict(os.environ, self.env):
            return update.verify(b"source", b"signature")

    def test_imports_the_checked_in_release_key(self):
        self.verify_with_gpg(validsig(PINNED_FINGERPRINT))

        invocations = self.log.read_text().splitlines()
        keyring = str(SCRIPTS.parent / "keys" / "gnupg-release.asc")
        self.assertTrue(any("--import" in line for line in invocations), invocations)
        self.assertTrue(any(keyring in line for line in invocations), invocations)

    def test_accepts_signature_from_pinned_fingerprint(self):
        self.assertIsNone(self.verify_with_gpg(validsig(PINNED_FINGERPRINT)))

    def test_rejects_signature_from_unpinned_fingerprint(self):
        with self.assertRaisesRegex(ValueError, "untrusted release signer") as caught:
            self.verify_with_gpg(validsig(UNPINNED_FINGERPRINT))

        self.assertIn(UNPINNED_FINGERPRINT, str(caught.exception))

    def test_rejects_any_unpinned_signer_in_a_multisigner_signature(self):
        status = validsig(PINNED_FINGERPRINT) + validsig(UNPINNED_FINGERPRINT)

        with self.assertRaisesRegex(ValueError, "untrusted release signer"):
            self.verify_with_gpg(status)

    def test_rejects_status_without_a_valid_signature(self):
        with self.assertRaisesRegex(ValueError, "untrusted release signer"):
            self.verify_with_gpg("[GNUPG:] NEWSIG\n")

    def test_propagates_gpg_failure(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify_with_gpg(validsig(PINNED_FINGERPRINT), exit_code=1)


if __name__ == "__main__":
    unittest.main()
