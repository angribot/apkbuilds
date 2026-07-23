#!/usr/bin/env python3
import argparse
import hashlib
import re
import subprocess
import tempfile
import time
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path

BASE = "https://gnupg.org/ftp/gcrypt/gnupg"
FINGERPRINTS = {
    "6DAA6E64A76D2840571B4902528897B826403ADA",
    "AC8E115BF73E2D8D47FA9908E98E9B2D19C6C8BD",
    "3B761AE4E63BF3519CE7D63BECB664CBE1332EEF",
    "02F38DFF731FF97CB039A1DA549E695E905BA208",
    "1493269DE61F124AA69A316E3ADF34EBDBB200A4",
}
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/gnupg/APKBUILD"
KEYRING = ROOT / "keys/gnupg-release.asc"


def download(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except HTTPError as error:
            if error.code not in (408, 429) and not 500 <= error.code < 600:
                raise
            last_error = error
        except (TimeoutError, URLError) as error:
            last_error = error
        if attempt < 2:
            time.sleep(2**attempt)
    raise last_error


def latest_version(index):
    versions = set(re.findall(r'href="gnupg-(\d+\.\d+\.\d+)\.tar\.bz2"', index))
    if not versions:
        raise ValueError("no stable releases found")
    return max(versions, key=lambda value: tuple(map(int, value.split("."))))


def current_version(text):
    match = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.MULTILINE)
    if not match:
        raise ValueError("pkgver not found")
    return match.group(1)


def updated_apkbuild(text, version, digest):
    old = current_version(text)
    text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^pkgrel=.*$", "pkgrel=0", text, count=1, flags=re.MULTILINE)
    pattern = rf"^[0-9a-f]{{128}}  gnupg-{re.escape(old)}\.tar\.bz2$"
    replacement = f"{digest}  gnupg-{version}.tar.bz2"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("source checksum not found")
    return text


def verify(source, signature):
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory) / "home"
        home.mkdir(mode=0o700)
        source_path = Path(directory) / "source.tar.bz2"
        signature_path = Path(directory) / "source.sig"
        source_path.write_bytes(source)
        signature_path.write_bytes(signature)
        subprocess.run(
            ["gpg", "--batch", "--homedir", str(home), "--import", str(KEYRING)],
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["gpg", "--batch", "--homedir", str(home), "--status-fd", "1", "--verify", str(signature_path), str(source_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    signers = {line.split()[2] for line in result.stdout.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")}
    if not signers or not signers <= FINGERPRINTS:
        raise ValueError(f"untrusted release signer: {signers}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = APKBUILD.read_text()
    version = latest_version(download(f"{BASE}/").decode())
    if version == current_version(text):
        print(version)
        return
    source = download(f"{BASE}/gnupg-{version}.tar.bz2")
    signature = download(f"{BASE}/gnupg-{version}.tar.bz2.sig")
    verify(source, signature)
    if args.check:
        raise SystemExit(f"update available: {version}")
    digest = hashlib.sha512(source).hexdigest()
    APKBUILD.write_text(updated_apkbuild(text, version, digest))
    print(version)


if __name__ == "__main__":
    main()
