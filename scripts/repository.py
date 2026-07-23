#!/usr/bin/env python3
import argparse
import json
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

PACKAGE_PATHS = {
    "gnupg": "packages/gnupg/",
    "zerostack": "packages/zerostack/",
}


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    origin: str
    checksum: str

    @property
    def filename(self):
        return f"{self.name}-{self.version}.apk"


def package_origins(paths):
    paths = list(paths)
    return sorted(
        origin
        for origin, directory in PACKAGE_PATHS.items()
        if any(path.startswith(directory) for path in paths)
    )


def component(value, field):
    if not value or any(char in value for char in "/\x00\n\r\t"):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def checksum(value):
    if not value or any(char in value for char in "\x00\n\r\t"):
        raise ValueError(f"invalid package checksum: {value!r}")
    return value


def read_index(path):
    with tarfile.open(path, "r:gz") as archive:
        try:
            member = archive.getmember("APKINDEX")
        except KeyError as error:
            raise ValueError("APKINDEX member not found") from error
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("APKINDEX member cannot be read")
        text = source.read().decode("utf-8")

    packages = {}
    for stanza in text.strip().split("\n\n"):
        fields = {}
        for line in stanza.splitlines():
            key, separator, value = line.partition(":")
            if separator and len(key) == 1:
                fields[key] = value
        missing = [field for field in ("P", "V", "o", "C") if not fields.get(field)]
        if missing:
            raise ValueError(f"package index entry missing {', '.join(missing)}")
        package = Package(
            component(fields["P"], "package name"),
            component(fields["V"], "package version"),
            component(fields["o"], "package origin"),
            checksum(fields["C"]),
        )
        if package.name in packages:
            raise ValueError(f"duplicate package in index: {package.name}")
        packages[package.name] = package
    if not packages:
        raise ValueError("package index is empty")
    return packages


def retained_packages(packages, origins):
    return {
        name: package
        for name, package in packages.items()
        if package.origin not in origins
    }


def verify_retained(previous, retained, origins):
    expected = retained_packages(previous, origins)
    if set(expected) != set(retained):
        missing = sorted(set(expected) - set(retained))
        unexpected = sorted(set(retained) - set(expected))
        raise ValueError(f"retained package set differs: missing={missing}, unexpected={unexpected}")
    for name, package in expected.items():
        if retained[name] != package:
            raise ValueError(f"retained package changed: {name}")


def replacements(previous, built, origins):
    built_origins = {package.origin for package in built.values()}
    unexpected = sorted(built_origins - origins)
    if unexpected:
        raise ValueError(f"built packages have unexpected origins: {unexpected}")
    missing = sorted(origins - built_origins)
    if missing:
        raise ValueError(f"selected origins produced no packages: {missing}")

    result = []
    for name, package in sorted(built.items()):
        old = previous.get(name)
        if old is None:
            continue
        if old.origin not in origins:
            raise ValueError(f"package changes origin without replacement scope: {name}")
        result.append((name, package.version, old.version))
    return result


def parse_origins(values):
    origins = set(values)
    unknown = sorted(origins - set(PACKAGE_PATHS))
    if unknown:
        raise ValueError(f"unknown package origins: {unknown}")
    if not origins:
        raise ValueError("no package origins selected")
    return origins


def command_scope(_args):
    print(json.dumps(package_origins(line.rstrip("\n") for line in sys.stdin), separators=(",", ":")))


def command_retained(args):
    origins = parse_origins(args.origin)
    packages = retained_packages(read_index(args.index), origins)
    for package in sorted(packages.values(), key=lambda item: item.filename):
        print(package.filename)


def command_verify_retained(args):
    verify_retained(read_index(args.previous_index), read_index(args.retained_index), parse_origins(args.origin))


def command_replacements(args):
    previous = read_index(args.previous_index) if args.previous_index else {}
    for name, new, old in replacements(previous, read_index(args.built_index), parse_origins(args.origin)):
        print(f"{name}\t{new}\t{old}")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    scope = commands.add_parser("scope")
    scope.set_defaults(handler=command_scope)

    retained = commands.add_parser("retained")
    retained.add_argument("--index", type=Path, required=True)
    retained.add_argument("--origin", action="append", default=[])
    retained.set_defaults(handler=command_retained)

    verify = commands.add_parser("verify-retained")
    verify.add_argument("--previous-index", type=Path, required=True)
    verify.add_argument("--retained-index", type=Path, required=True)
    verify.add_argument("--origin", action="append", default=[])
    verify.set_defaults(handler=command_verify_retained)

    compare = commands.add_parser("replacements")
    compare.add_argument("--previous-index", type=Path)
    compare.add_argument("--built-index", type=Path, required=True)
    compare.add_argument("--origin", action="append", default=[])
    compare.set_defaults(handler=command_replacements)

    args = parser.parse_args()
    try:
        args.handler(args)
    except (OSError, UnicodeDecodeError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"repository.py: {error}\n")


if __name__ == "__main__":
    main()
