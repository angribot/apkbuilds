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

UPSTREAM_REPOSITORY = "https://github.com/Yuu518/ports-box"
RELEASES = "https://api.github.com/repos/Yuu518/ports-box/releases?per_page=100"
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/ports-box/APKBUILD"


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


def declared_version(text):
    match = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.MULTILINE)
    if not match:
        raise ValueError("pkgver not found")
    return match.group(1)


def newest_eligible_release(releases):
    # The source archive is pinned by checksum, never built from a moving
    # branch, so only strict non-draft, non-prerelease vX.Y.Z tags qualify.
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        match = re.fullmatch(r"v(\d+\.\d+\.\d+)", release.get("tag_name", ""))
        if not match:
            continue
        candidates.append((version_key(match.group(1)), match.group(1)))
    if not candidates:
        raise ValueError("no eligible upstream releases found")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def updated_apkbuild(text, version, digest):
    old = declared_version(text)
    text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^pkgrel=.*$", "pkgrel=0", text, count=1, flags=re.MULTILINE)
    pattern = rf"^[0-9a-f]{{128}}  ports-box-{re.escape(old)}\.tar\.gz$"
    replacement = f"{digest}  ports-box-{version}.tar.gz"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("source checksum not found")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    text = APKBUILD.read_text()
    releases = json.loads(download(RELEASES))
    version = newest_eligible_release(releases)
    if version_key(version) <= version_key(declared_version(text)):
        print(declared_version(text))
        return
    source = download(f"{UPSTREAM_REPOSITORY}/archive/refs/tags/v{version}.tar.gz")
    digest = hashlib.sha512(source).hexdigest()
    if args.check:
        raise SystemExit(f"update available: {version}")
    APKBUILD.write_text(updated_apkbuild(text, version, digest))
    print(version)


if __name__ == "__main__":
    main()
