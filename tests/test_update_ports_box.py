import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "update_ports_box", Path(__file__).parents[1] / "scripts/update-ports-box.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def release(tag, **values):
    result = {"tag_name": tag, "draft": False, "prerelease": False}
    result.update(values)
    return result


class UpdatePortsBoxTest(unittest.TestCase):
    def test_newest_eligible_release_requires_strict_version_tag(self):
        version = update.newest_eligible_release(
            [
                release("v2.0.0-rc1"),
                release("v1.10.0", prerelease=True),
                release("v1.9.0", draft=True),
                release("v1.8.0"),
                release("nightly"),
            ]
        )
        self.assertEqual(version, "1.8.0")

    def test_update_resets_revision_and_checksum(self):
        text = "pkgver=0.1.2\npkgrel=2\n" + "a" * 128 + "  ports-box-0.1.2.tar.gz\n"
        result = update.updated_apkbuild(text, "0.1.3", "b" * 128)
        self.assertIn("pkgver=0.1.3\npkgrel=0", result)
        self.assertIn("b" * 128 + "  ports-box-0.1.3.tar.gz", result)

    def test_update_rejects_missing_checksum(self):
        with self.assertRaisesRegex(ValueError, "source checksum"):
            update.updated_apkbuild("pkgver=0.1.2\npkgrel=0\n", "0.1.3", "b" * 128)

    def test_main_pins_archive_checksum_from_strict_tag(self):
        # The sha512 written into the APKBUILD must match what abuild verifies
        # against the upstream archive at the strict version tag.
        data = b"source archive"
        digest = hashlib.sha512(data).hexdigest()
        releases = json.dumps([release("v0.1.3")]).encode()
        apkbuild = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.addCleanup(pathlib.Path(apkbuild.name).unlink)
        apkbuild.write("pkgver=0.1.2\npkgrel=0\n" + "a" * 128 + "  ports-box-0.1.2.tar.gz\n")
        apkbuild.close()

        def download(url):
            if url.endswith("/releases?per_page=100"):
                return releases
            return data

        with mock.patch.object(update, "download", side_effect=download), \
                mock.patch.object(update, "APKBUILD", pathlib.Path(apkbuild.name)):
            update.main([])
        self.assertIn("pkgver=0.1.3\npkgrel=0", pathlib.Path(apkbuild.name).read_text())
        self.assertIn(digest + "  ports-box-0.1.3.tar.gz", pathlib.Path(apkbuild.name).read_text())


if __name__ == "__main__":
    unittest.main()
