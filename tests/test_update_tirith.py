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

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "update_tirith", SCRIPTS / "update-tirith.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def release(tag, **values):
    result = {"tag_name": tag, "draft": False, "prerelease": False}
    result.update(values)
    return result


class UpdateTirithTest(unittest.TestCase):
    def test_newest_eligible_release_requires_strict_version_tag(self):
        version = update.newest_eligible_release(
            [
                release("v1.0.0-rc1"),
                release("v0.5.0", prerelease=True),
                release("v0.4.0", draft=True),
                release("v0.3.4"),
                release("nightly"),
            ]
        )
        self.assertEqual(version, "0.3.4")

    def test_newest_eligible_release_ignores_threat_database_releases(self):
        version = update.newest_eligible_release(
            [
                release("threatdb-27540228085-1"),
                release("threatdb-latest"),
                release("v0.3.3"),
            ]
        )
        self.assertEqual(version, "0.3.3")

    def test_fetch_releases_paginates_past_threat_database_releases(self):
        first_page = [release(f"threatdb-{number}-1") for number in range(100)]
        second_page = [release("v0.3.4")]
        pages = [
            json.dumps(first_page).encode(),
            json.dumps(second_page).encode(),
        ]

        with mock.patch.object(update, "download", side_effect=pages) as download:
            releases = update.fetch_releases()

        self.assertEqual(update.newest_eligible_release(releases), "0.3.4")
        self.assertEqual(
            [call.args[0] for call in download.call_args_list],
            [f"{update.RELEASES}&page=1", f"{update.RELEASES}&page=2"],
        )

    def test_update_rejects_missing_checksum(self):
        with self.assertRaisesRegex(ValueError, "source checksum"):
            update.updated_apkbuild("pkgver=0.3.3\npkgrel=0\n", "0.3.4", "b" * 128)

    def test_main_pins_archive_checksum_from_strict_tag(self):
        data = b"source archive"
        digest = hashlib.sha512(data).hexdigest()
        apkbuild = self.temporary_apkbuild("0.3.3")

        def download(url):
            if url == f"{update.RELEASES}&page=1":
                return json.dumps([release("v0.3.4")]).encode()
            return data

        with mock.patch.object(update, "download", side_effect=download), mock.patch.object(
            update, "APKBUILD", apkbuild
        ), redirect_stdout(StringIO()):
            update.main([])

        text = apkbuild.read_text()
        self.assertIn("pkgver=0.3.4\npkgrel=0", text)
        self.assertIn(digest + "  tirith-0.3.4.tar.gz", text)

    def test_main_leaves_declared_build_unchanged_without_upgrade(self):
        apkbuild = self.temporary_apkbuild("0.3.3")
        original = apkbuild.read_text()

        with mock.patch.object(
            update,
            "download",
            return_value=json.dumps([release("v0.3.3")]).encode(),
        ) as download, mock.patch.object(update, "APKBUILD", apkbuild), redirect_stdout(
            StringIO()
        ) as stdout:
            update.main([])

        self.assertEqual(apkbuild.read_text(), original)
        self.assertEqual(stdout.getvalue(), "0.3.3\n")
        download.assert_called_once_with(f"{update.RELEASES}&page=1")

    def temporary_apkbuild(self, version):
        apkbuild = tempfile.NamedTemporaryFile(mode="w", delete=False)
        path = Path(apkbuild.name)
        self.addCleanup(path.unlink)
        apkbuild.write(
            f"pkgver={version}\npkgrel=2\n"
            + "a" * 128
            + f"  tirith-{version}.tar.gz\n"
        )
        apkbuild.close()
        return path


if __name__ == "__main__":
    unittest.main()
