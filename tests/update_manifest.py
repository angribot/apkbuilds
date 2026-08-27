"""Shared reader for the package-origin updater manifest."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "packages" / "updaters"


def read_manifest():
    return tuple(
        tuple(line.split("|"))
        for line in MANIFEST_PATH.read_text().splitlines()
        if line and not line.startswith("#")
    )
