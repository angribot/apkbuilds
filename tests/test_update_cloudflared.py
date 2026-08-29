import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "update_cloudflared", SCRIPTS / "update-cloudflared.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def release(tag, **values):
    result = {"tag_name": tag, "draft": False, "prerelease": False}
    result.update(values)
    return result


class UpdateCloudflaredTest(unittest.TestCase):
    def test_newest_eligible_release_requires_strict_calver_tag(self):
        version = update.newest_eligible_release(
            [
                release("2026.10.0"),
                release("2026.9.2"),
                release("2026.09.3"),
                release("v2026.11.0"),
                release("2026.12.0-rc1"),
                release("2026.13.0", prerelease=True),
                release("2026.14.0", draft=True),
                release(None),
            ]
        )

        self.assertEqual(version, "2026.10.0")

    def test_newest_eligible_release_returns_none_when_no_release_qualifies(self):
        self.assertIsNone(
            update.newest_eligible_release(
                [release("2026.10.0-rc1"), release("nightly")]
            )
        )

    def test_update_resets_revision_and_replaces_archive_checksum(self):
        text = (
            "pkgver=2026.7.3\npkgrel=4\n"
            + "a" * 128
            + "  cloudflared-2026.7.3.tar.gz\n"
        )

        result = update.updated_apkbuild(text, "2026.8.2", "b" * 128)

        self.assertIn("pkgver=2026.8.2\npkgrel=0", result)
        self.assertIn("b" * 128 + "  cloudflared-2026.8.2.tar.gz", result)

    def test_main_hashes_the_source_archive_for_the_selected_release(self):
        source = b"cloudflared source archive"
        digest = hashlib.sha512(source).hexdigest()
        apkbuild = self.temporary_apkbuild("2026.7.3")

        def download(url):
            if url == update.RELEASES:
                return json.dumps([release("2026.8.2")]).encode()
            self.assertEqual(
                url,
                "https://github.com/cloudflare/cloudflared/"
                "archive/refs/tags/2026.8.2.tar.gz",
            )
            return source

        with mock.patch.object(update, "download", side_effect=download), mock.patch.object(
            update, "APKBUILD", apkbuild
        ), redirect_stdout(StringIO()):
            update.main([])

        text = apkbuild.read_text()
        self.assertIn("pkgver=2026.8.2\npkgrel=0", text)
        self.assertIn(digest + "  cloudflared-2026.8.2.tar.gz", text)

    def test_check_leaves_package_origin_unchanged_without_newer_release(self):
        apkbuild = self.temporary_apkbuild("2026.8.2")
        original = apkbuild.read_text()

        with mock.patch.object(
            update,
            "download",
            return_value=json.dumps([release("2026.8.2"), release("2026.7.3")]).encode(),
        ) as download, mock.patch.object(update, "APKBUILD", apkbuild), redirect_stdout(
            StringIO()
        ) as stdout:
            update.main(["--check"])

        self.assertEqual(apkbuild.read_text(), original)
        self.assertEqual(stdout.getvalue(), "2026.8.2\n")
        download.assert_called_once_with(update.RELEASES)

    def temporary_apkbuild(self, version):
        apkbuild = tempfile.NamedTemporaryFile(mode="w", delete=False)
        path = Path(apkbuild.name)
        self.addCleanup(path.unlink)
        apkbuild.write(
            f"pkgver={version}\npkgrel=4\n"
            + "a" * 128
            + f"  cloudflared-{version}.tar.gz\n"
        )
        apkbuild.close()
        return path


if __name__ == "__main__":
    unittest.main()
