import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "update_zerostack", SCRIPTS / "update-zerostack.py"
)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)

ASSET_NAMES = [a.name for a in update.ASSETS.values()]


def release(tag, assets=ASSET_NAMES, **values):
    result = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in assets],
    }
    result.update(values)
    return result


class UpdateZerostackTest(unittest.TestCase):
    def test_newest_eligible_release_requires_version_tag_and_both_assets(self):
        version, assets = update.newest_eligible_release(
            [
                release("v2.0.0-rc1"),
                release("v1.10.0", prerelease=True),
                release("v1.9.0", assets=ASSET_NAMES[:1]),
                release("v1.8.0"),
                release("v1.7.0"),
            ]
        )
        self.assertEqual(version, "1.8.0")
        self.assertEqual(set(assets), {"x86_64", "aarch64"})

    def test_update_resets_revision_checksums_and_architectures(self):
        text = (
            'pkgver=1.7.0\npkgrel=2\narch="x86_64 !aarch64"\n'
            "case \"$CARCH\" in\n"
            f"x86_64)\n\t_sha512=\"{'a' * 128}\"\n\t;;\n"
            f"aarch64)\n\t_sha512=\"{'b' * 128}\"\n\t;;\nesac\n"
        )
        digests = {"x86_64": "c" * 128, "aarch64": "d" * 128}
        excluded_arch_result = update.updated_apkbuild(text, "1.7.2", digests)
        self.assertIn('arch="x86_64 !aarch64"', excluded_arch_result)

        result = update.updated_apkbuild(text, "1.8.0", digests)
        self.assertIn('pkgver=1.8.0\npkgrel=0\narch="x86_64 aarch64"', result)
        self.assertIn(f'x86_64)\n\t_sha512="{"c" * 128}"', result)
        self.assertIn(f'aarch64)\n\t_sha512="{"d" * 128}"', result)


if __name__ == "__main__":
    unittest.main()
