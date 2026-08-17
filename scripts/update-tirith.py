#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

from update import bump_apkbuild_version, declared_version, download, version_key

UPSTREAM_REPOSITORY = "https://github.com/sheeki03/tirith"
RELEASES = "https://api.github.com/repos/sheeki03/tirith/releases?per_page=100"
RELEASES_PER_PAGE = 100
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/tirith/APKBUILD"


def fetch_releases():
    releases = []
    page = 1
    while True:
        batch = json.loads(download(f"{RELEASES}&page={page}"))
        if not isinstance(batch, list):
            raise ValueError("invalid upstream releases response")
        releases.extend(batch)
        if len(batch) < RELEASES_PER_PAGE:
            return releases
        page += 1


def newest_eligible_release(releases):
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
    text = bump_apkbuild_version(text, version)
    pattern = rf"^[0-9a-f]{{128}}  tirith-{re.escape(old)}\.tar\.gz$"
    replacement = f"{digest}  tirith-{version}.tar.gz"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("source checksum not found")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    text = APKBUILD.read_text()
    current_version = declared_version(text)
    version = newest_eligible_release(fetch_releases())
    if version_key(version) <= version_key(current_version):
        print(current_version)
        return
    source = download(f"{UPSTREAM_REPOSITORY}/archive/refs/tags/v{version}.tar.gz")
    digest = hashlib.sha512(source).hexdigest()
    if args.check:
        raise SystemExit(f"update available: {version}")
    APKBUILD.write_text(updated_apkbuild(text, version, digest))
    print(version)


if __name__ == "__main__":
    main()
