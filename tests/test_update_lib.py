import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("update", SCRIPTS / "update.py")
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


class UpdateLibTest(unittest.TestCase):
    def test_version_key_parses_semver(self):
        self.assertEqual(update.version_key("1.2.3"), (1, 2, 3))
        self.assertEqual(update.version_key("0.10.0"), (0, 10, 0))

    def test_declared_version_extracts_pkgver(self):
        text = "pkgver=2.5.21\npkgrel=1\n"
        self.assertEqual(update.declared_version(text), "2.5.21")

    def test_declared_version_rejects_missing_pkgver(self):
        with self.assertRaisesRegex(ValueError, "pkgver not found"):
            update.declared_version("pkgname=example\npkgrel=1\n")

    def test_verified_sha512_rejects_github_digest_mismatch(self):
        data = b"release asset"
        digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
        self.assertEqual(
            update.verified_sha512(data, digest), hashlib.sha512(data).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            update.verified_sha512(data, "sha256:" + "0" * 64)

    @mock.patch.dict(update.os.environ, {"GITHUB_TOKEN": "secret"})
    @mock.patch.object(update.urllib.request, "urlopen")
    def test_download_sends_token_only_to_github_api(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b""
        update.download("https://api.github.com/repos/example/releases")
        self.assertEqual(
            urlopen.call_args.args[0].get_header("Authorization"), "Bearer secret"
        )
        update.download("https://github.com/example/releases/download/asset")
        self.assertIsNone(urlopen.call_args.args[0].get_header("Authorization"))

    @mock.patch.object(update.urllib.request, "urlopen")
    def test_download_exposes_the_first_acquisition_failure(self, urlopen):
        from urllib.error import HTTPError

        error = HTTPError("https://example.com", 503, "Service Unavailable", {}, None)
        recovery = mock.MagicMock()
        recovery.__enter__.return_value.read.return_value = b"unexpected retry"
        urlopen.side_effect = [error, recovery]

        with self.assertRaises(HTTPError):
            update.download("https://example.com/release")

        self.assertEqual(urlopen.call_count, 1)

    def test_bump_apkbuild_version_updates_pkgver_and_resets_pkgrel(self):
        text = "pkgver=1.2.3\npkgrel=5\n"
        result = update.bump_apkbuild_version(text, "1.3.0")
        self.assertIn("pkgver=1.3.0", result)
        self.assertIn("pkgrel=0", result)


if __name__ == "__main__":
    unittest.main()
