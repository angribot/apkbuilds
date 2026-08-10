"""Shared updater skeleton for Alpine package updaters."""

import hashlib
import os
import re
import time
import urllib.request
from typing import NamedTuple
from urllib.error import HTTPError, URLError


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
    """Download *url* with retry and backoff, returning the response body."""
    headers = {"User-Agent": "apkbuilds-updater"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(url, headers=headers)
    last_error = None
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


def verified_sha512(data, github_digest):
    """Verify *data* against *github_digest* and return its sha512 hex string."""
    match = re.fullmatch(r"sha256:([0-9a-f]{64})", github_digest or "")
    if not match:
        raise ValueError("invalid GitHub asset digest")
    if hashlib.sha256(data).hexdigest() != match.group(1):
        raise ValueError("GitHub asset digest mismatch")
    return hashlib.sha512(data).hexdigest()
