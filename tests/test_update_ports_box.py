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
    "update_ports_box", SCRIPTS / "update-ports-box.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


class UpdatePortsBoxTest(unittest.TestCase):
    def test_main_updates_the_origin_from_its_upstream_archive(self):
        self.assertEqual(update.APKBUILD, SCRIPTS.parent / "packages/ports-box/APKBUILD")
        source = b"ports-box source archive"
        with tempfile.TemporaryDirectory() as directory:
            apkbuild = Path(directory) / "ports-box" / "APKBUILD"
            apkbuild.parent.mkdir()
            apkbuild.write_text(
                "pkgver=0.1.2\npkgrel=1\n" + "a" * 128 + "  ports-box-0.1.2.tar.gz\n"
            )
            responses = {
                "https://api.github.com/repos/Yuu518/ports-box/releases?per_page=100":
                    json.dumps([{"tag_name": "v0.1.3"}]).encode(),
                "https://github.com/Yuu518/ports-box/archive/refs/tags/v0.1.3.tar.gz": source,
            }
            with mock.patch.object(shared_update, "download", side_effect=responses.__getitem__), \
                    mock.patch.object(update, "APKBUILD", apkbuild):
                update.main([])
            self.assertEqual(
                apkbuild.read_text(),
                "pkgver=0.1.3\npkgrel=0\n"
                + hashlib.sha512(source).hexdigest() + "  ports-box-0.1.3.tar.gz\n",
            )


if __name__ == "__main__":
    unittest.main()
