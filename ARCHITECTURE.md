# Architecture

## Directory Layout

- [`README.md`](README.md) — repository installation and upgrade instructions.
- [`packages/gnupg/`](packages/gnupg/) — Alpine edge's GnuPG APKBUILD, package
  split functions, install hook, udev rule, and downstream patches.
- [`packages/zerostack/`](packages/zerostack/) — architecture-specific APKBUILD
  for upstream's static musl zerostack binaries.
- [`scripts/update.py`](scripts/update.py) — detects stable upstream GnuPG
  releases, verifies their signatures, and updates `pkgver`, `pkgrel`, and
  checksum.
- [`scripts/update-zerostack.py`](scripts/update-zerostack.py) — selects complete
  stable zerostack releases, verifies both GitHub asset digests, and updates the
  architecture-specific checksums.
- [`scripts/test-package.sh`](scripts/test-package.sh) — installed GnuPG smoke
  test covering version reporting, key generation, signing, and verification.
- [`keys/gnupg-release.asc`](keys/gnupg-release.asc) — checked-in upstream
  release public keys; accepted fingerprints remain pinned in `update.py`.
- [`keys/apkbuilds.rsa.pub`](keys/apkbuilds.rsa.pub) — persistent repository
  signing public key; its private key exists only in the protected `release`
  GitHub Environment.
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — updater tests and
  native `x86_64`/`aarch64` Alpine edge builds and smoke tests for every package.
- [`.github/workflows/update.yml`](.github/workflows/update.yml) — daily update
  PR creation and automatic merge request.
- [`.github/workflows/publish.yml`](.github/workflows/publish.yml) — isolated
  build, smoke-test, offline signing, Pages publication, and remote installation
  tests after successful current-main CI.
- [`tests/test_update.py`](tests/test_update.py) and
  [`tests/test_update_zerostack.py`](tests/test_update_zerostack.py) —
  standard-library updater unit tests.

## Key Types and Relationships

The project is script-oriented and defines no domain classes or traits. The
GnuPG updater selects release-shaped tarballs and accepts only signatures from
`FINGERPRINTS`. The zerostack updater selects exact stable tags only when both
musl assets exist, verifies their GitHub-provided SHA-256 digests, and records
SHA-512 checksums. Alpine `abuild` consumes both APKBUILDs; zerostack selects its
pinned binary and checksum from `CARCH`.

## Control Flow

1. `update.yml` runs daily at 00:00 UTC or manually, with one matrix job per
   package.
2. Each updater compares stable upstream releases with its APKBUILD version.
3. GnuPG source is signature-verified; both zerostack assets are checked against
   GitHub's SHA-256 metadata. Each verified change gets a package-specific PR
   and CI run, then auto-merges after both native builds pass.
4. `ci.yml` tests non-documentation changes. PR and manual update runs build
   both packages independently on native x86_64 and ARM64 runners; main pushes
   leave package builds to the publishing workflow to avoid duplicate work.
5. Successful CI for current main runs the isolated publication flow below and
   deploys verified repositories under `edge/x86_64` and `edge/aarch64`.
6. The deployment includes its tested commit SHA. Native post-deployment jobs
   wait for that marker, download the exact GnuPG and zerostack APKs from the
   architecture repository, install them, and repeat their smoke tests.
7. Failed detection, verification, build, publication, or smoke tests stop their
   workflow.

## Data Flow

The GnuPG release index supplies signed source and an authenticated SHA-512
digest; GitHub Releases supplies complete zerostack assets whose SHA-256
metadata is verified before recording SHA-512. `abuild -r` compiles GnuPG and
packages zerostack with an ephemeral key. A read-only container tests the staged
packages; a network-disabled signer replaces package and index signatures with
the persistent key.

## Design Decisions

- Track stable upstream GnuPG rather than Alpine's LTS-only version policy.
- Retain Alpine edge's GnuPG package split, build options, patches, and
  dependencies to minimize divergence; dependency packages are not maintained
  here.
- Package zerostack's upstream static musl binaries directly; APKBUILD does not
  require a compile phase, and native CI verifies both supported artifacts.
- Ignore draft, prerelease, incomplete, and non-`vX.Y.Z` zerostack releases;
  never downgrade when the GitHub API returns an older complete release.
- Pin release-key fingerprints in code in addition to checking in upstream keys
  so replacing the key file alone cannot authorize a source.
- Use native GitHub-hosted runners (`ubuntu-24.04` and `ubuntu-24.04-arm`), with
  no QEMU complexity while ARM runners are available.
- Use only Python and shell standard tooling; no project dependencies are added.
- Publish automatically only after successful CI for the current main SHA;
  serialize deployments so post-deployment verification is never cancelled.
- Verify Pages propagation with the deployed commit marker, then install the
  exact Pages-hosted GnuPG and zerostack APK files so Alpine packages cannot
  satisfy the smoke tests accidentally.

## External Dependencies

- Alpine edge repositories provide `alpine-sdk`, build dependencies, and runtime
  dependencies declared by the APKBUILD.
- GnuPG's official HTTPS server provides the release index, source, signature,
  and public release keys.
- GitHub Releases provides zerostack release metadata, asset digests, and static
  musl binaries.
- GnuPG verifies source signatures; `abuild` creates staged APKs and supplies
  the offline package/index signing tools.
- GitHub Actions supplies scheduling, native runners, checks, PRs, merging, and
  Pages deployment.

## Entry Points and Execution Modes

- Scheduled/manual updates: `python3 scripts/update.py` and
  `python3 scripts/update-zerostack.py`, via `update.yml`.
- Local update checks: run either updater with `--check`.
- Unit tests: `python3 -m unittest discover -s tests`.
- CI/manual package build: `ci.yml`; locally, run `abuild -r` from the desired
  directory under [`packages/`](packages/) in an Alpine edge `alpine-sdk` setup.
- Automatic Pages publication: `publish.yml`, after successful CI for the
  current main SHA.
- Public repository: `https://angribot.github.io/apkbuilds/edge`; `apk` appends
  the current architecture when fetching its index.
