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
                "pkgver=0.1.3\npkgrel=2\n"
                'source="ports-box-$pkgver.tar.gz::https://github.com/Yuu518/ports-box/'
                'archive/refs/tags/v$pkgver.tar.gz\n\tports-box.initd\n\t"\n'
                'sha512sums="\n'
                + "a" * 128 + "  ports-box-0.1.3.tar.gz\n"
                + "b" * 128 + '  ports-box.initd\n"\n'
            )
            responses = {
                "https://api.github.com/repos/Yuu518/ports-box/releases?per_page=100":
                    json.dumps([
                        {"tag_name": "0.3.0", "draft": False, "prerelease": False},
                        {"tag_name": "0.2.0", "draft": False, "prerelease": False},
                    ]).encode(),
                "https://github.com/Yuu518/ports-box/archive/refs/tags/0.3.0.tar.gz": source,
            }
            with mock.patch.object(shared_update, "download", side_effect=responses.__getitem__), \
                    mock.patch.object(update, "APKBUILD", apkbuild):
                update.main([])
            self.assertEqual(
                apkbuild.read_text(),
                "pkgver=0.3.0\npkgrel=0\n"
                'source="ports-box-$pkgver.tar.gz::https://github.com/Yuu518/ports-box/'
                'archive/refs/tags/$pkgver.tar.gz\n\tports-box.initd\n\t"\n'
                'sha512sums="\n'
                + hashlib.sha512(source).hexdigest() + "  ports-box-0.3.0.tar.gz\n"
                + "b" * 128 + '  ports-box.initd\n"\n',
            )


if __name__ == "__main__":
    unittest.main()
