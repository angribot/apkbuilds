import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import update as shared_update

SPEC = importlib.util.spec_from_file_location(
    "update_zerostack", SCRIPTS / "update-zerostack.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


class UpdateZerostackTest(unittest.TestCase):
    def test_main_updates_the_origin_from_its_upstream_archive(self):
        self.assertEqual(update.APKBUILD, SCRIPTS.parent / "packages/zerostack/APKBUILD")
        source = b"zerostack source archive"
        with tempfile.TemporaryDirectory() as directory:
            apkbuild = Path(directory) / "zerostack" / "APKBUILD"
            apkbuild.parent.mkdir()
            apkbuild.write_text(
                "pkgver=1.7.2\npkgrel=1\n" + "a" * 128 + "  zerostack-1.7.2.tar.gz\n"
            )
            responses = {
                "https://api.github.com/repos/gi-dellav/zerostack/releases?per_page=100":
                    json.dumps([{"tag_name": "v1.7.3"}]).encode(),
                "https://github.com/gi-dellav/zerostack/archive/refs/tags/v1.7.3.tar.gz": source,
            }
            with mock.patch.object(shared_update, "download", side_effect=responses.__getitem__), \
                    mock.patch.object(update, "APKBUILD", apkbuild):
                update.main([])
            self.assertEqual(
                apkbuild.read_text(),
                "pkgver=1.7.3\npkgrel=0\n"
                + hashlib.sha512(source).hexdigest() + "  zerostack-1.7.3.tar.gz\n",
            )


if __name__ == "__main__":
    unittest.main()
