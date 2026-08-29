#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

from update import bump_apkbuild_version, declared_version, download, version_key

UPSTREAM_REPOSITORY = "https://github.com/cloudflare/cloudflared"
RELEASES = "https://api.github.com/repos/cloudflare/cloudflared/releases?per_page=100"
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/cloudflared/APKBUILD"
VERSION_TAG = re.compile(
    r"([0-9]{4}\.(?:[1-9]|1[0-2])\.(?:0|[1-9][0-9]*))"
)
RELEASE_PAGE_SIZE = 100


def upstream_releases():
    page = 1
    while True:
        url = RELEASES if page == 1 else f"{RELEASES}&page={page}"
        releases = json.loads(download(url))
        if not isinstance(releases, list):
            raise ValueError("unexpected GitHub releases response")
        yield from releases
        if len(releases) < RELEASE_PAGE_SIZE:
            return
        page += 1


def newest_eligible_release(releases):
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag_name = release.get("tag_name")
        if not isinstance(tag_name, str):
            continue
        match = VERSION_TAG.fullmatch(tag_name)
        if match:
            version = match.group(1)
            candidates.append((version_key(version), version))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[0])[1]


def updated_apkbuild(text, version, digest):
    old = declared_version(text)
    if not re.fullmatch(r"[0-9a-f]{128}", digest):
        raise ValueError("invalid source checksum")
    text = bump_apkbuild_version(text, version)
    pattern = rf"^[0-9a-f]{{128}}  cloudflared-{re.escape(old)}\.tar\.gz$"
    replacement = f"{digest}  cloudflared-{version}.tar.gz"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("source checksum not found")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    text = APKBUILD.read_text()
    releases = upstream_releases()
    version = newest_eligible_release(releases)
    declared = declared_version(text)
    if version is None or version_key(version) <= version_key(declared):
        print(declared)
        return

    source = download(f"{UPSTREAM_REPOSITORY}/archive/refs/tags/{version}.tar.gz")
    digest = hashlib.sha512(source).hexdigest()
    if args.check:
        raise SystemExit(f"update available: {version}")

    APKBUILD.write_text(updated_apkbuild(text, version, digest))
    print(version)


if __name__ == "__main__":
    main()
