import importlib.util
import sys
import unittest
from pathlib import Path

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

    def test_update_resets_revision_and_replaces_each_architecture_checksum(self):
        text = (
            "pkgver=2.9.4\npkgrel=2\n"
            'x86_64)\n\t_sha512="' + "a" * 128 + '"\n'
            'aarch64)\n\t_sha512="' + "b" * 128 + '"\n'
        )

        result = update.updated_apkbuild(
            text,
            "2.10.0",
            {"x86_64": "c" * 128, "aarch64": "d" * 128},
        )

        self.assertIn("pkgver=2.10.0\npkgrel=0", result)
        self.assertIn('x86_64)\n\t_sha512="' + "c" * 128 + '"', result)
        self.assertIn('aarch64)\n\t_sha512="' + "d" * 128 + '"', result)


if __name__ == "__main__":
    unittest.main()
