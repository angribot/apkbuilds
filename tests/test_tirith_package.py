"""Packaging contracts for the Tirith source build."""

import hashlib
import pathlib
import re
import subprocess
import tarfile
import tempfile
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
APKBUILD = ROOT / "packages" / "tirith" / "APKBUILD"
PATCH = ROOT / "packages" / "tirith" / "0001-add-apk-install-method.patch"


class TirithPackageTest(unittest.TestCase):
    def test_downstream_patch_applies_to_pinned_source(self):
        """Keep the package patch applicable to the source it declares."""
        apkbuild = APKBUILD.read_text()
        version = re.search(r"^pkgver=(\S+)$", apkbuild, re.MULTILINE).group(1)
        source = re.search(
            r"tirith-\$pkgver\.tar\.gz::([^\s]+)", apkbuild
        ).group(1).replace("$pkgver", version)
        expected_sha512 = re.search(
            rf"^([0-9a-f]{{128}})  tirith-{re.escape(version)}\.tar\.gz$",
            apkbuild,
            re.MULTILINE,
        ).group(1)

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with urllib.request.urlopen(source, timeout=30) as response:
                archive = response.read()
            self.assertEqual(hashlib.sha512(archive).hexdigest(), expected_sha512)
            archive_path = root / "source.tar.gz"
            archive_path.write_bytes(archive)
            with tarfile.open(archive_path) as tar:
                tar.extractall(root)

            source_dir = root / f"tirith-{version}"
            completed = subprocess.run(
                ["patch", "--batch", "--dry-run", "--forward", "-p1"],
                cwd=source_dir,
                input=PATCH.read_text(),
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
