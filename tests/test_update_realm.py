import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "update_realm", SCRIPTS / "update-realm.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def release(tag, assets, **values):
    result = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in assets],
    }
    result.update(values)
    return result


class UpdateRealmTest(unittest.TestCase):
    def test_newest_eligible_release_requires_both_architecture_assets(self):
        assets = [asset.name for asset in update.ASSETS.values()]

        version, selected = update.newest_eligible_release(
            [
                release("v3.0.0", assets[:1]),
                release("v2.10.0", assets),
                release("v2.9.5", assets, prerelease=True),
            ]
        )

        self.assertEqual(version, "2.10.0")
        self.assertEqual(set(selected), {"x86_64", "aarch64"})

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.apkbuild = Path(directory.name) / "APKBUILD"
        self.original = (
            "pkgver=2.9.4\npkgrel=2\n"
            'x86_64)\n\t_sha512="' + "a" * 128 + '"\n'
            'aarch64)\n\t_sha512="' + "b" * 128 + '"\n'
        )
        self.apkbuild.write_text(self.original)
        self.assets = [
            {
                "name": f"realm-{arch}-unknown-linux-musl.tar.gz",
                "browser_download_url": (
                    "https://github.com/zhboner/realm/releases/download/v2.10.0/"
                    f"realm-{arch}-unknown-linux-musl.tar.gz"
                ),
                "digest": "sha256:" + hashlib.sha256(arch.encode()).hexdigest(),
            }
            for arch in ("x86_64", "aarch64")
        ]

    def run_update(self, argv=()):
        responses = {
            "https://api.github.com/repos/zhboner/realm/releases?per_page=100":
                json.dumps([{"tag_name": "v2.10.0", "assets": self.assets}]).encode(),
            **{
                asset["browser_download_url"]: arch.encode()
                for arch, asset in zip(("x86_64", "aarch64"), self.assets)
            },
        }
        with mock.patch.object(update, "APKBUILD", self.apkbuild), \
                mock.patch.object(update, "download", side_effect=responses.__getitem__), \
                mock.patch.object(sys, "argv", ["update-realm.py", *argv]), \
                redirect_stdout(io.StringIO()):
            update.main()

    def test_main_updates_both_architecture_checksums_after_authentication(self):
        self.run_update()
        self.assertEqual(
            self.apkbuild.read_text(),
            "pkgver=2.10.0\npkgrel=0\n"
            'x86_64)\n\t_sha512="' + hashlib.sha512(b"x86_64").hexdigest() + '"\n'
            'aarch64)\n\t_sha512="' + hashlib.sha512(b"aarch64").hexdigest() + '"\n',
        )

    def test_main_rejects_unexpected_asset_urls_without_writing(self):
        for asset in self.assets:
            with self.subTest(asset=asset["name"]), mock.patch.dict(
                asset, {"browser_download_url": "https://example.invalid/asset"}
            ):
                with self.assertRaisesRegex(ValueError, "unexpected .* asset URL"):
                    self.run_update()
                self.assertEqual(self.apkbuild.read_text(), self.original)

    def test_main_rejects_invalid_asset_digests_without_partial_writes(self):
        for asset in self.assets:
            for digest in (None, "sha256:" + "0" * 64):
                with self.subTest(asset=asset["name"], digest=digest):
                    with mock.patch.dict(asset, {"digest": digest}):
                        with self.assertRaisesRegex(ValueError, "GitHub asset digest"):
                            self.run_update()
                    self.assertEqual(self.apkbuild.read_text(), self.original)

    def test_check_authenticates_both_assets_without_writing(self):
        with self.assertRaisesRegex(SystemExit, "update available: 2.10.0"):
            self.run_update(["--check"])
        self.assertEqual(self.apkbuild.read_text(), self.original)


if __name__ == "__main__":
    unittest.main()
