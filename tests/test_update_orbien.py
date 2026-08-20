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
    "update_orbien", SCRIPTS / "update-orbien.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def release(tag, **values):
    result = {"tag_name": tag, "draft": False, "prerelease": False}
    result.update(values)
    return result


class UpdateOrbienTest(unittest.TestCase):
    def test_newest_eligible_release_requires_strict_version_tag(self):
        version = update.newest_eligible_release(
            [
                release("v4.0.0-rc1"),
                release("v03.1.0"),
                release("v1٢.2.3"),
                release(None),
                release("v3.3.0", prerelease=True),
                release("v3.2.0", draft=True),
                release("v3.1.0"),
                release("3.4.0"),
                release("nightly"),
            ]
        )

        self.assertEqual(version, "3.1.0")

    def test_newest_eligible_release_uses_semantic_version_order(self):
        version = update.newest_eligible_release(
            [release("v3.9.0"), release("v3.10.0"), release("v3.2.10")]
        )

        self.assertEqual(version, "3.10.0")

    def test_update_resets_revision_and_replaces_archive_checksum(self):
        text = "pkgver=3.1.0\npkgrel=4\n" + "a" * 128 + "  orbien-3.1.0.tar.gz\n"

        result = update.updated_apkbuild(text, "3.2.0", "b" * 128)

        self.assertIn("pkgver=3.2.0\npkgrel=0", result)
        self.assertIn("b" * 128 + "  orbien-3.2.0.tar.gz", result)

    def test_update_rejects_missing_archive_checksum(self):
        with self.assertRaisesRegex(ValueError, "source checksum"):
            update.updated_apkbuild(
                "pkgver=3.1.0\npkgrel=1\n", "3.2.0", "b" * 128
            )

    def test_main_pins_checksum_of_strict_tag_archive(self):
        source = b"orbien source archive"
        digest = hashlib.sha512(source).hexdigest()
        apkbuild = self.temporary_apkbuild("3.1.0")

        def download(url):
            if url == update.RELEASES:
                return json.dumps([release("v3.2.0")]).encode()
            return source

        with mock.patch.object(update, "download", side_effect=download), mock.patch.object(
            update, "APKBUILD", apkbuild
        ), redirect_stdout(StringIO()):
            update.main([])

        text = apkbuild.read_text()
        self.assertIn("pkgver=3.2.0\npkgrel=0", text)
        self.assertIn(digest + "  orbien-3.2.0.tar.gz", text)

    def test_main_leaves_package_origin_unchanged_without_newer_release(self):
        apkbuild = self.temporary_apkbuild("3.1.0")
        original = apkbuild.read_text()

        with mock.patch.object(
            update,
            "download",
            return_value=json.dumps([release("v3.1.0"), release("v3.0.0")]).encode(),
        ) as download, mock.patch.object(update, "APKBUILD", apkbuild), redirect_stdout(
            StringIO()
        ) as stdout:
            update.main(["--check"])

        self.assertEqual(apkbuild.read_text(), original)
        self.assertEqual(stdout.getvalue(), "3.1.0\n")
        download.assert_called_once_with(update.RELEASES)

    def test_main_leaves_package_origin_unchanged_without_eligible_release(self):
        apkbuild = self.temporary_apkbuild("3.1.0")
        original = apkbuild.read_text()

        with mock.patch.object(
            update,
            "download",
            return_value=json.dumps(
                [release("v3.2.0", prerelease=True), release("nightly")]
            ).encode(),
        ) as download, mock.patch.object(update, "APKBUILD", apkbuild), redirect_stdout(
            StringIO()
        ) as stdout:
            update.main(["--check"])

        self.assertEqual(apkbuild.read_text(), original)
        self.assertEqual(stdout.getvalue(), "3.1.0\n")
        download.assert_called_once_with(update.RELEASES)

    def temporary_apkbuild(self, version):
        apkbuild = tempfile.NamedTemporaryFile(mode="w", delete=False)
        path = Path(apkbuild.name)
        self.addCleanup(path.unlink)
        apkbuild.write(
            f"pkgver={version}\npkgrel=4\n"
            + "a" * 128
            + f"  orbien-{version}.tar.gz\n"
        )
        apkbuild.close()
        return path


if __name__ == "__main__":
    unittest.main()
