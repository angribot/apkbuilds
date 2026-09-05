import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from urllib.error import URLError

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import update


class SourceArchiveUpdaterTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.apkbuild = Path(directory.name) / "example" / "APKBUILD"
        self.apkbuild.parent.mkdir()
        self.original = (
            "pkgver=1.9.0\npkgrel=3\nsha512sums=\"\n"
            + "a" * 128 + "  example-1.9.0.tar.gz\n"
            + "b" * 128 + "  downstream.patch\n\"\n"
        )
        self.apkbuild.write_text(self.original)
        self.source = b"source archive"
        self.download = mock.Mock(side_effect=[
            json.dumps([{"tag_name": "v1.10.0"}]).encode(), self.source,
        ])
        patcher = mock.patch.object(update, "download", self.download)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.stdout = io.StringIO()

    def run_update(self, argv=()):
        with redirect_stdout(self.stdout):
            update.update_source_archive("owner/upstream", self.apkbuild, argv)

    def test_updates_to_newest_eligible_release_and_preserves_patch_checksum(self):
        self.download.side_effect = [json.dumps([
            {"tag_name": "v2.0.0-rc1"},
            {"tag_name": "v2.0.0", "prerelease": True},
            {"tag_name": "v3.0.0", "draft": True},
            {"tag_name": "nightly"},
            {"tag_name": "v1.10.0"},
            {"tag_name": "v1.9.1"},
        ]).encode(), self.source]
        self.run_update()
        self.assertEqual(self.apkbuild.read_text(), (
            "pkgver=1.10.0\npkgrel=0\nsha512sums=\"\n"
            + hashlib.sha512(self.source).hexdigest() + "  example-1.10.0.tar.gz\n"
            + "b" * 128 + "  downstream.patch\n\"\n"
        ))
        self.assertEqual(self.stdout.getvalue(), "1.10.0\n")
        self.assertEqual(self.download.call_args_list, [
            mock.call("https://api.github.com/repos/owner/upstream/releases?per_page=100"),
            mock.call("https://github.com/owner/upstream/archive/refs/tags/v1.10.0.tar.gz"),
        ])

    def test_same_or_older_release_does_not_download_archive_or_write(self):
        for version in ("1.9.0", "1.8.0"):
            with self.subTest(version=version):
                self.download.reset_mock()
                self.download.side_effect = [json.dumps([{"tag_name": f"v{version}"}]).encode()]
                self.stdout = io.StringIO()
                self.run_update()
                self.assertEqual(self.apkbuild.read_text(), self.original)
                self.assertEqual(self.stdout.getvalue(), "1.9.0\n")
                self.assertEqual(self.download.call_count, 1)

    def test_no_eligible_release_fails_without_writing(self):
        self.download.side_effect = [b"[]"]
        with self.assertRaisesRegex(ValueError, "no eligible upstream releases found"):
            self.run_update()
        self.assertEqual(self.apkbuild.read_text(), self.original)

    def test_check_downloads_archive_but_does_not_write(self):
        with self.assertRaisesRegex(SystemExit, "update available: 1.10.0"):
            self.run_update(["--check"])
        self.assertEqual(self.apkbuild.read_text(), self.original)
        self.assertEqual(self.download.call_count, 2)
        self.assertEqual(self.stdout.getvalue(), "")

    def test_download_failure_is_not_retried_and_leaves_file_unchanged(self):
        for stage in ("releases", "archive"):
            with self.subTest(stage=stage):
                self.download.reset_mock()
                responses = [URLError("acquisition failed")]
                if stage == "archive":
                    responses.insert(0, json.dumps([{"tag_name": "v1.10.0"}]).encode())
                self.download.side_effect = responses
                with self.assertRaisesRegex(URLError, "acquisition failed"):
                    self.run_update()
                self.assertEqual(self.download.call_count, len(responses))
                self.assertEqual(self.apkbuild.read_text(), self.original)

    def test_missing_source_checksum_fails_without_writing(self):
        original = "pkgver=1.9.0\npkgrel=3\n"
        self.apkbuild.write_text(original)
        with self.assertRaisesRegex(ValueError, "source checksum not found"):
            self.run_update()
        self.assertEqual(self.apkbuild.read_text(), original)


if __name__ == "__main__":
    unittest.main()
