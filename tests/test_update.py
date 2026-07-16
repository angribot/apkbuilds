import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("update", Path(__file__).parents[1] / "scripts/update.py")
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


class UpdateTest(unittest.TestCase):
    def test_latest_version_ignores_non_release_files(self):
        index = '<a href="gnupg-2.5.9.tar.bz2">x</a><a href="gnupg-2.5.10.tar.bz2">x</a><a href="gnupg-2.6.0-beta.tar.bz2">x</a>'
        self.assertEqual(update.latest_version(index), "2.5.10")

    def test_latest_version_rejects_empty_index(self):
        with self.assertRaisesRegex(ValueError, "no stable releases"):
            update.latest_version("")

    def test_update_resets_release_and_checksum(self):
        text = "pkgver=2.4.9\npkgrel=3\n" + "a" * 128 + "  gnupg-2.4.9.tar.bz2\n"
        result = update.updated_apkbuild(text, "2.5.21", "b" * 128)
        self.assertIn("pkgver=2.5.21\npkgrel=0", result)
        self.assertIn("b" * 128 + "  gnupg-2.5.21.tar.bz2", result)

    def test_update_rejects_missing_checksum(self):
        with self.assertRaisesRegex(ValueError, "source checksum"):
            update.updated_apkbuild("pkgver=2.4.9\npkgrel=0\n", "2.5.21", "b" * 128)


if __name__ == "__main__":
    unittest.main()
