#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path

REPOSITORY = "https://github.com/gi-dellav/zerostack"
RELEASES = "https://api.github.com/repos/gi-dellav/zerostack/releases?per_page=100"
ASSETS = {
    "x86_64": "zerostack-x86_64-unknown-linux-musl.tar.gz",
    "aarch64": "zerostack-aarch64-unknown-linux-musl.tar.gz",
}
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/zerostack/APKBUILD"


def download(url):
    headers = {"User-Agent": "apkbuilds-updater"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
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


def version_key(version):
    return tuple(map(int, version.split(".")))


def current_version(text):
    match = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.MULTILINE)
    if not match:
        raise ValueError("pkgver not found")
    return match.group(1)


def latest_release(releases):
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        match = re.fullmatch(r"v(\d+\.\d+\.\d+)", release.get("tag_name", ""))
        if not match:
            continue
        available = {
            asset.get("name"): asset
            for asset in release.get("assets", [])
            if isinstance(asset, dict)
        }
        if not all(name in available for name in ASSETS.values()):
            continue
        version = match.group(1)
        candidates.append(
            (version_key(version), version, {arch: available[name] for arch, name in ASSETS.items()})
        )
    if not candidates:
        raise ValueError("no stable releases with musl binaries found")
    _, version, assets = max(candidates, key=lambda candidate: candidate[0])
    return version, assets


def verified_sha512(data, github_digest):
    match = re.fullmatch(r"sha256:([0-9a-f]{64})", github_digest or "")
    if not match:
        raise ValueError("invalid GitHub asset digest")
    if hashlib.sha256(data).hexdigest() != match.group(1):
        raise ValueError("GitHub asset digest mismatch")
    return hashlib.sha512(data).hexdigest()


def updated_apkbuild(text, version, digests):
    text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^pkgrel=.*$", "pkgrel=0", text, count=1, flags=re.MULTILINE)
    for arch in ASSETS:
        digest = digests.get(arch, "")
        if not re.fullmatch(r"[0-9a-f]{128}", digest):
            raise ValueError(f"invalid {arch} source checksum")
        pattern = rf'(?m)(^{arch}\)\n[ \t]+_sha512=")[0-9a-f]{{128}}(")$'
        text, count = re.subn(
            pattern,
            lambda match: f"{match.group(1)}{digest}{match.group(2)}",
            text,
            count=1,
        )
        if count != 1:
            raise ValueError(f"{arch} source checksum not found")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    text = APKBUILD.read_text()
    releases = json.loads(download(RELEASES))
    version, assets = latest_release(releases)
    current = current_version(text)
    if version_key(version) <= version_key(current):
        print(current)
        return

    digests = {}
    for arch, name in ASSETS.items():
        url = f"{REPOSITORY}/releases/download/v{version}/{name}"
        asset = assets[arch]
        if asset.get("browser_download_url") != url:
            raise ValueError(f"unexpected {arch} asset URL")
        digests[arch] = verified_sha512(download(url), asset.get("digest"))

    if args.check:
        raise SystemExit(f"update available: {version}")
    APKBUILD.write_text(updated_apkbuild(text, version, digests))
    print(version)


if __name__ == "__main__":
    main()
