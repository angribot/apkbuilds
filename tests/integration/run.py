#!/usr/bin/env python3
"""Exercise the public repository operations using real native Docker containers."""

import argparse
from functools import partial
import gzip
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from threading import Thread
import zlib

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
ORIGIN = "apkbuilds-ci-probe"
ARCHITECTURES = ("x86_64", "aarch64")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_digests(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def indexed_packages(directory):
    # Signed APKINDEX archives contain concatenated signature/index streams.
    with tarfile.open(directory / "APKINDEX.tar.gz", "r:gz", ignore_zeros=True) as archive:
        index = archive.extractfile("APKINDEX").read().decode()
    packages = set()
    for record in index.strip().split("\n\n"):
        fields = dict(line.split(":", 1) for line in record.splitlines() if ":" in line)
        packages.add(f"{fields['P']}-{fields['V']}.apk")
    return packages


def damage_signature(path):
    compressed = zlib.decompressobj(wbits=31)
    signature = bytearray(compressed.decompress(path.read_bytes()))
    with tarfile.open(fileobj=io.BytesIO(signature), mode="r:") as archive:
        member = next((entry for entry in archive
                       if Path(entry.name).name.startswith(".SIGN.") and entry.isfile()), None)
    require(member is not None and member.size > 0, "expected an APK v2 signature member")
    # Keep the tar header and package data intact; alter one signature byte.
    signature[member.offset_data] ^= 1
    path.write_bytes(gzip.compress(signature, mtime=0) + compressed.unused_data)


class Lifecycle:
    def __init__(self, root, arch, logs):
        self.root = root
        self.arch = arch
        self.other_arch = next(item for item in ARCHITECTURES if item != arch)
        self.logs = logs
        self.workspace = root / "workspace"
        self.private_key = root / "private" / "apkbuilds.rsa"
        self.published = root / "published"
        self.server = None
        self.server_thread = None
        self.counter = 0
        self.env = os.environ.copy()
        for name in ("ABUILD_PRIVATE_KEY", "PAGES_DEPLOY_KEY", "UPDATE_DEPLOY_KEY",
                     "GITHUB_OUTPUT", "GIT_DIR", "GIT_WORK_TREE"):
            self.env.pop(name, None)
        self.env.update({
            "GITHUB_WORKSPACE": str(self.workspace),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        })

    def run(self, name, command, *, env=None, expected_error=None):
        self.counter += 1
        log = self.logs / f"{self.counter:02d}-{name}.log"
        print(f"==> {name}", flush=True)
        with log.open("w") as output:
            completed = subprocess.run(
                list(map(str, command)), env=self.env | (env or {}),
                stdout=output, stderr=subprocess.STDOUT, text=True, timeout=600,
            )
        text = log.read_text()
        if expected_error is not None:
            ok = completed.returncode != 0 and expected_error in text
        else:
            ok = completed.returncode == 0
        if not ok:
            print(text[-16000:], flush=True)
            raise RuntimeError(f"{name} returned {completed.returncode}; see {log}")
        return text.strip()

    def reclaim(self):
        # Real containers write root/builder-owned files into bind mounts.
        self.run("reclaim-files", [
            "docker", "run", "--rm", "--network", "none",
            "-v", f"{self.root}:/work", "alpine:edge",
            "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work",
        ])

    def operation(self, name, script, runner, *arguments, env=None, expected_error=None):
        runner.mkdir(exist_ok=True)
        output = runner / f"{name}.output"
        self.run(name, ["sh", self.workspace / "scripts" / script, *arguments], env={
            "RUNNER_TEMP": str(runner), "GITHUB_OUTPUT": str(output), **(env or {}),
        }, expected_error=expected_error)
        return dict(line.split("=", 1) for line in output.read_text().splitlines()) \
            if output.exists() else {}

    def build(self, name, *, expected_error=None):
        # A fresh runner directory proves a no-op cannot reuse old candidates.
        runner = self.root / name
        outputs = self.operation(
            name, "build-package-family.sh", runner,
            "--origin", ORIGIN, "--arch", self.arch,
            "--source-revision", self.revision,
            "--published", f"{self.url}/edge/{self.arch}",
            expected_error=expected_error,
        )
        self.reclaim()
        return runner, outputs

    def setup(self):
        self.run("docker-ready", ["docker", "info"])
        actual = self.run("native-architecture", [
            "docker", "run", "--rm", "alpine:edge", "apk", "--print-arch",
        ]).splitlines()[-1]
        require(actual == self.arch, f"expected native {self.arch}, got {actual}")
        self.revision = self.run("source-revision", ["git", "-C", ROOT, "rev-parse", "HEAD"])
        shutil.copytree(ROOT / "scripts", self.workspace / "scripts")
        shutil.copytree(FIXTURES / "probe", self.workspace / "packages" / ORIGIN)
        (self.workspace / "keys").mkdir()
        self.private_key.parent.mkdir(mode=0o700)
        self.run("temporary-private-key", ["openssl", "genrsa", "-out", self.private_key, "2048"])
        self.private_key.chmod(0o600)
        self.run("temporary-public-key", [
            "openssl", "rsa", "-in", self.private_key, "-pubout",
            "-out", self.workspace / "keys" / "apkbuilds.rsa.pub",
        ])
        seed = self.root / "seed"
        seed.mkdir()
        self.run("signed-baseline", [
            "docker", "run", "--rm",
            "-v", f"{seed}:/seed",
            "-v", f"{self.workspace}:/workspace:ro",
            "-v", f"{self.private_key}:/private-key:ro",
            "-v", f"{FIXTURES}:/fixtures:ro",
            "-v", f"{ROOT / 'tests/integration/bootstrap.sh'}:/bootstrap.sh:ro",
            "alpine:edge", "sh", "/bootstrap.sh",
        ])
        self.reclaim()
        shutil.copytree(seed / "pages", self.published)
        # Bind only the local Docker bridge, not all host interfaces. The
        # harness and daemon must share a Linux host (as on GitHub runners).
        address = self.run("baseline-address", [
            "docker", "network", "inspect", "bridge", "--format",
            "{{(index .IPAM.Config 0).Gateway}}",
        ])
        require(address, "Docker's default bridge has no gateway")
        handler = partial(SimpleHTTPRequestHandler, directory=str(self.published))
        self.server = ThreadingHTTPServer((address, 0), handler)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.url = f"http://{address}:{self.server.server_port}"
        self.run("baseline-reachable", [
            "docker", "run", "--rm", "alpine:edge", "wget", "-q", "-O", "/dev/null",
            f"{self.url}/edge/{self.arch}/APKINDEX.tar.gz",
        ])

    def upgrade(self):
        _, outputs = self.build("build-new-family")
        require(outputs.get("built") == "true", "new family was not built")
        candidates = Path(outputs["artifact"])
        expected = {f"{ORIGIN}-2.0.0-r0.apk", f"{ORIGIN}-data-2.0.0-r0.apk"}
        require({p.name for p in (candidates / self.arch / ORIGIN).glob("*.apk")} == expected,
                "candidate family differs from the fixture contract")
        release = self.root / "release"
        release.mkdir()
        pages = release / "pages"
        shutil.copytree(self.published, pages)
        shutil.copytree(candidates, release / "built")
        untouched = file_digests(pages / "edge" / self.other_arch)
        unrelated = pages / "edge" / self.arch / "apkbuilds-ci-unrelated-1.0.0-r0.apk"
        unrelated_bytes = unrelated.read_bytes()
        other_index = indexed_packages(pages / "edge" / self.other_arch)
        signed = self.operation("sign-new-family", "sign-repository.sh", release, env={
            "ABUILD_PRIVATE_KEY": self.private_key.read_text(),
        })
        self.reclaim()
        require(signed.get("snapshot_created") == "true", "signer emitted no snapshot")
        require(not (release / "repository-signing-key").exists(), "signer left its key behind")
        current = pages / "edge" / self.arch
        expected.add(unrelated.name)
        require({p.name for p in current.glob("*.apk")} == expected,
                "old family was not replaced completely")
        require(indexed_packages(current) == expected, "index differs from physical packages")
        require(unrelated.read_bytes() == unrelated_bytes, "unrelated APK changed")
        other = pages / "edge" / self.other_arch
        # Indexes are regenerated by the signer; compare their package set and
        # APK bytes, not timestamp-dependent compressed index bytes.
        require(indexed_packages(other) == other_index, "other architecture's index changed")
        require({p.name for p in other.glob("*.apk")} == other_index,
                "other architecture's physical package set changed")
        for name, digest in untouched.items():
            if name.endswith(".apk"):
                require(hashlib.sha256((other / name).read_bytes()).hexdigest() == digest,
                        f"other architecture's APK changed: {name}")
        self.operation("verify-install", "verify-repository.sh", release,
                       "--arch", self.arch, "--install-declared-builds")
        smoke = self.run("execute-installed-probe", [
            "docker", "run", "--rm", "--network", "none",
            "-v", f"{pages}:/pages:ro", "alpine:edge", "sh", "-ec",
            'cp /pages/apkbuilds.rsa.pub /etc/apk/keys/\n'
            'printf "%s\\n" /pages/edge > /etc/apk/repositories\n'
            f'apk add --no-cache {ORIGIN}=2.0.0-r0\n'
            f'apk info -e {ORIGIN}-data\n'
            f'{ORIGIN}',
        ])
        require("apkbuilds-ci-probe: split payload" in smoke, "installed native probe failed")
        shutil.copytree(pages, self.published, dirs_exist_ok=True)
        # Remove retired baseline files from the served snapshot as well.
        for path in (self.published / "edge" / self.arch).glob("*.apk"):
            if path.name not in expected:
                path.unlink()
        return release

    def no_op_and_conflict(self):
        runner, outputs = self.build("already-published")
        require(outputs.get("built") == "false", "published family was rebuilt")
        require(not list((runner / "new" / "built").rglob("*.apk")), "no-op left candidates")
        signed = self.operation("no-candidate-snapshot", "sign-repository.sh", runner)
        require(signed.get("snapshot_created") == "false", "no-op created a snapshot")
        apkbuild = self.workspace / "packages" / ORIGIN / "APKBUILD"
        original = apkbuild.read_text()
        try:
            apkbuild.write_text(original.replace('subpackages="$pkgname-data::noarch"',
                                                'subpackages=""'))
            runner, _ = self.build("identity-conflict", expected_error="stage=build-identity")
            require(not list((runner / "new" / "built").rglob("*.apk")),
                    "identity conflict produced candidates")
        finally:
            apkbuild.write_text(original)

    def corruption(self, release):
        package = release / "pages" / "edge" / self.arch / f"{ORIGIN}-2.0.0-r0.apk"
        original = package.read_bytes()
        try:
            damage_signature(package)
            self.operation("reject-damaged-signature", "verify-repository.sh", release,
                           "--arch", self.arch, expected_error="stage=signature")
        finally:
            package.write_bytes(original)

    def publish(self, release):
        snapshot = self.root / "snapshot"
        shutil.copytree(release / "pages", snapshot)
        expected = file_digests(snapshot)
        remote = self.root / "remote.git"
        self.run("local-remote", ["git", "init", "--bare", remote])
        self.operation("publish-local-snapshot", "publish-repository.sh", release,
                       str(snapshot), self.revision, str(remote),
                       env={"PAGES_DEPLOY_KEY": "local-transport-does-not-use-ssh"})
        revision = self.run("published-revision", [
            "git", "-C", remote, "log", "-1", "--format=%s", "gh-pages",
        ])
        require(revision == f"Publish {self.revision}", "publication lost source revision")
        checkout = self.root / "published-checkout"
        self.run("published-checkout", ["git", "clone", "--branch", "gh-pages", remote, checkout])
        shutil.rmtree(checkout / ".git")
        require(file_digests(checkout) == expected, "published tree differs from verified snapshot")

    def cleanup(self):
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
                self.server_thread.join()
        finally:
            self.reclaim()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=ARCHITECTURES)
    parser.add_argument("--logs", type=Path, default=ROOT / ".cache" / "ci-integration")
    args = parser.parse_args()
    for executable in ("docker", "git", "openssl"):
        require(shutil.which(executable), f"{executable} is required")
    logs = args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apkbuilds-integration-") as directory:
        root = Path(directory)
        # The unprivileged builder must traverse directories inside bind mounts.
        root.chmod(0o755)
        lifecycle = Lifecycle(root, args.arch, logs)
        try:
            lifecycle.setup()
            release = lifecycle.upgrade()
            lifecycle.no_op_and_conflict()
            lifecycle.corruption(release)
            lifecycle.publish(release)
            print(f"Integration passed on {args.arch}", flush=True)
        finally:
            lifecycle.cleanup()


if __name__ == "__main__":
    main()
