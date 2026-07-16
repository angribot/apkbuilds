# Architecture

## Directory Layout

- [`packages/gnupg/`](packages/gnupg/) — Alpine edge's GnuPG APKBUILD, package
  split functions, install hook, udev rule, and downstream patches.
- [`scripts/update.py`](scripts/update.py) — detects stable upstream releases,
  verifies their signatures, and updates `pkgver`, `pkgrel`, and checksum.
- [`scripts/test-package.sh`](scripts/test-package.sh) — installed-package smoke
  test covering version reporting, key generation, signing, and verification.
- [`keys/gnupg-release.asc`](keys/gnupg-release.asc) — checked-in upstream
  release public keys; accepted fingerprints remain pinned in `update.py`.
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — updater tests and
  native `x86_64`/`aarch64` Alpine edge builds.
- [`.github/workflows/update.yml`](.github/workflows/update.yml) — daily update
  PR creation and automatic merge request.
- [`tests/test_update.py`](tests/test_update.py) — standard-library unit tests.

## Key Types and Relationships

The project is script-oriented and defines no domain classes or traits.
`latest_version()` selects only release-shaped tarballs; `verify()` accepts only
valid signatures from `FINGERPRINTS`; `updated_apkbuild()` performs the minimal
APKBUILD mutation. Alpine `abuild` consumes the shell variables and package
split functions in [`packages/gnupg/APKBUILD`](packages/gnupg/APKBUILD).

## Control Flow

1. `update.yml` runs daily at 00:00 UTC or manually.
2. `update.py` compares the official release index with the APKBUILD version.
3. A new source and detached signature are downloaded and verified before any
   file changes. A verified update produces a PR and requests auto-merge.
4. `ci.yml` tests every PR, then builds independently on native x86_64 and ARM64
   runners in Alpine edge. Each resulting repository is installed and tested.
5. Failed detection, verification, build, or smoke tests stop the workflow; no
   update is merged.

## Data Flow

The official HTML index yields a semantic version. The corresponding tarball
and signature yield an authenticated source and SHA-512 digest. These values
replace `pkgver` and the source checksum in the APKBUILD. `abuild -r` downloads
sources, applies Alpine patches, compiles GnuPG, splits it into APK subpackages,
and creates a temporary signed package repository. `apk add` installs the
`gnupg` metapackage from that repository for end-to-end tests.

## Design Decisions

- Track stable upstream GnuPG rather than Alpine's LTS-only version policy.
- Retain Alpine edge's package split, build options, patches, and dependencies
  to minimize divergence; dependency packages are not maintained here.
- Pin release-key fingerprints in code in addition to checking in upstream keys
  so replacing the key file alone cannot authorize a source.
- Use native GitHub-hosted runners (`ubuntu-24.04` and `ubuntu-24.04-arm`), with
  no QEMU complexity while ARM runners are available.
- Use only Python and shell standard tooling; no project dependencies are added.
- Publishing and persistent abuild signing are deferred until both architecture
  builds pass and the owner provisions a dedicated abuild key.

## External Dependencies

- Alpine edge repositories provide `alpine-sdk`, build dependencies, and runtime
  dependencies declared by the APKBUILD.
- GnuPG's official HTTPS server provides the release index, source, signature,
  and public release keys.
- GnuPG verifies source signatures; `abuild` builds and temporarily signs APKs.
- GitHub Actions supplies scheduling, native runners, checks, PRs, and merging.

## Entry Points and Execution Modes

- Scheduled/manual update: `python3 scripts/update.py`, via `update.yml`.
- Local update check: `python3 scripts/update.py --check`.
- Unit tests: `python3 -m unittest discover -s tests`.
- CI/manual package build: `ci.yml`; locally, run `abuild -r` from
  [`packages/gnupg/`](packages/gnupg/) in an Alpine edge `alpine-sdk` setup.
