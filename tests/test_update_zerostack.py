import hashlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "update_zerostack", Path(__file__).parents[1] / "scripts/update-zerostack.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)

ASSETS = list(update.ASSETS.values())


def release(tag, assets=ASSETS, **values):
    result = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in assets],
    }
    result.update(values)
    return result


class UpdateZerostackTest(unittest.TestCase):
    def test_newest_eligible_release_requires_version_tag_and_both_assets(self):
        version, assets = update.newest_eligible_release(
            [
                release("v2.0.0-rc1"),
                release("v1.10.0", prerelease=True),
                release("v1.9.0", assets=ASSETS[:1]),
                release("v1.8.0"),
                release("v1.7.0"),
            ]
        )
        self.assertEqual(version, "1.8.0")
        self.assertEqual(set(assets), {"x86_64", "aarch64"})

    def test_newest_eligible_release_rejects_missing_release(self):
        with self.assertRaisesRegex(ValueError, "no eligible upstream releases"):
            update.newest_eligible_release([])

    def test_update_resets_revision_checksums_and_architectures(self):
        text = (
            'pkgver=1.7.0\npkgrel=2\narch="x86_64 !aarch64"\n'
            "case \"$CARCH\" in\n"
            f"x86_64)\n\t_sha512=\"{'a' * 128}\"\n\t;;\n"
            f"aarch64)\n\t_sha512=\"{'b' * 128}\"\n\t;;\nesac\n"
        )
        digests = {"x86_64": "c" * 128, "aarch64": "d" * 128}
        excluded_arch_result = update.updated_apkbuild(text, "1.7.2", digests)
        self.assertIn('arch="x86_64 !aarch64"', excluded_arch_result)

        result = update.updated_apkbuild(text, "1.8.0", digests)
        self.assertIn('pkgver=1.8.0\npkgrel=0\narch="x86_64 aarch64"', result)
        self.assertIn(f'x86_64)\n\t_sha512="{"c" * 128}"', result)
        self.assertIn(f'aarch64)\n\t_sha512="{"d" * 128}"', result)

    def test_verified_sha512_rejects_github_digest_mismatch(self):
        data = b"release asset"
        digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
        self.assertEqual(update.verified_sha512(data, digest), hashlib.sha512(data).hexdigest())
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


if __name__ == "__main__":
    unittest.main()
