"""Shared mechanisms and source archive workflow for Alpine package updaters."""

import argparse
import hashlib
import json
import os
import re
import urllib.request
from typing import NamedTuple


class ArchAsset(NamedTuple):
    """An architecture-specific upstream release asset."""

    arch: str
    name: str


class CandidateRelease(NamedTuple):
    """A candidate upstream release with its version and architecture assets."""

    version_key: tuple[int, ...]
    version: str
    assets: dict[str, dict]


def download(url):
    """Download *url* once, returning the response body."""
    headers = {"User-Agent": "apkbuilds-updater"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def bump_apkbuild_version(text, version):
    """Update pkgver and reset pkgrel in APKBUILD *text*."""
    text = re.sub(r"^pkgver=.*$", f"pkgver={version}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^pkgrel=.*$", "pkgrel=0", text, count=1, flags=re.MULTILINE)
    return text


def version_key(version):
    """Parse *version* into a comparable tuple of integers."""
    return tuple(map(int, version.split(".")))


def declared_version(text):
    """Extract the declared pkgver from APKBUILD *text*."""
    match = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.MULTILINE)
    if not match:
        raise ValueError("pkgver not found")
    return match.group(1)


def update_source_archive(repository, apkbuild, argv=None):
    """Update a GitHub tag archive for the package origin containing apkbuild.

    repository is the GitHub owner/name; the archive basename is the origin's
    directory name. Only non-draft, non-prerelease vX.Y.Z releases qualify.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    text = apkbuild.read_text()
    releases = json.loads(download(
        f"https://api.github.com/repos/{repository}/releases?per_page=100"
    ))
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        match = re.fullmatch(r"v(\d+\.\d+\.\d+)", release.get("tag_name", ""))
        if match:
            candidates.append((version_key(match.group(1)), match.group(1)))
    if not candidates:
        raise ValueError("no eligible upstream releases found")
    version = max(candidates, key=lambda candidate: candidate[0])[1]
    declared = declared_version(text)
    if version_key(version) <= version_key(declared):
        print(declared)
        return

    source = download(
        f"https://github.com/{repository}/archive/refs/tags/v{version}.tar.gz"
    )
    digest = hashlib.sha512(source).hexdigest()
    if args.check:
        raise SystemExit(f"update available: {version}")

    origin = apkbuild.parent.name
    text = bump_apkbuild_version(text, version)
    pattern = rf"^[0-9a-f]{{128}}  {re.escape(origin)}-{re.escape(declared)}\.tar\.gz$"
    text, count = re.subn(
        pattern, f"{digest}  {origin}-{version}.tar.gz", text,
        count=1, flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("source checksum not found")
    apkbuild.write_text(text)
    print(version)


def verified_sha512(data, github_digest):
    """Verify *data* against *github_digest* and return its sha512 hex string."""
    match = re.fullmatch(r"sha256:([0-9a-f]{64})", github_digest or "")
    if not match:
        raise ValueError("invalid GitHub asset digest")
    if hashlib.sha256(data).hexdigest() != match.group(1):
        raise ValueError("GitHub asset digest mismatch")
    return hashlib.sha512(data).hexdigest()
