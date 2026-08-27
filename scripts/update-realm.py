#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

from update import ArchAsset, CandidateRelease, bump_apkbuild_version, declared_version, download, verified_sha512, version_key

UPSTREAM_REPOSITORY = "https://github.com/zhboner/realm"
RELEASES = "https://api.github.com/repos/zhboner/realm/releases?per_page=100"
ASSETS = {
    "x86_64": ArchAsset("x86_64", "realm-x86_64-unknown-linux-musl.tar.gz"),
    "aarch64": ArchAsset("aarch64", "realm-aarch64-unknown-linux-musl.tar.gz"),
}
ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/realm/APKBUILD"


def newest_eligible_release(releases):
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
        if not all(asset.name in available for asset in ASSETS.values()):
            continue
        version = match.group(1)
        candidates.append(
            CandidateRelease(
                version_key(version),
                version,
                {arch: available[asset.name] for arch, asset in ASSETS.items()},
            )
        )
    if not candidates:
        raise ValueError("no eligible upstream releases with musl binaries found")
    best = max(candidates, key=lambda c: c.version_key)
    return best.version, best.assets


def updated_apkbuild(text, version, digests):
    text = bump_apkbuild_version(text, version)
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
    version, assets = newest_eligible_release(releases)
    declared = declared_version(text)
    if version_key(version) <= version_key(declared):
        print(declared)
        return

    digests = {}
    for arch, arch_asset in ASSETS.items():
        url = f"{UPSTREAM_REPOSITORY}/releases/download/v{version}/{arch_asset.name}"
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
