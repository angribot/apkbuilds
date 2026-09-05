#!/usr/bin/env python3
from pathlib import Path

from update import update_source_archive

ROOT = Path(__file__).resolve().parents[1]
APKBUILD = ROOT / "packages/zerostack/APKBUILD"


def main(argv=None):
    update_source_archive("gi-dellav/zerostack", APKBUILD, argv)


if __name__ == "__main__":
    main()
