# Architecture

## Design Decisions

- Track stable upstream GnuPG rather than Alpine's LTS-only version policy.
- Retain Alpine edge's GnuPG package split, build options, patches, and
  dependencies to minimize divergence; dependency packages are not maintained here.
- Package zerostack's upstream static musl binaries directly; APKBUILD does not
  require a compile phase, and native CI verifies both supported artifacts.
- Ignore draft, prerelease, incomplete, and non-`vX.Y.Z` zerostack releases;
  never downgrade when the GitHub API returns an older complete release.
- Pin release-key fingerprints in code in addition to checking in upstream keys
  so replacing the key file alone cannot authorize a source.
- Use native GitHub-hosted runners (`ubuntu-24.04` and `ubuntu-24.04-arm`), with
  no QEMU complexity while ARM runners are available.
- Use only Python and shell standard tooling; no project dependencies are added.
- Build only changed source-package groups; GnuPG's split packages are one atomic
  group, while zerostack is independent.
- Publish architectures independently: a failed architecture retains its last
  verified APK snapshot while successful architectures advance. Assemble one
  serialized Pages snapshot and track one published commit marker per architecture.
- Assemble publication snapshots from release-key-verified unchanged APKs and new
  package outputs; replacements must increase their package version. Reset
  `pkgrel` to `0` when `pkgver` changes; otherwise increment `pkgrel`.
- Keep update merging in the trusted default-branch workflow; merge only a
  bot-owned, single-APKBUILD PR at the exact SHA whose updater checks pass and
  at least one architecture builds. Select the CI run to watch by head SHA,
  since a recreated branch can leave earlier runs that match by branch name and
  event alone.
- Dispatch read-only CI after merging an update; its eligible `workflow_run`
  triggers publication. Manual publication is limited to first-release
  bootstrap. Serialize deployments so post-deployment verification is never
  cancelled.
- Prepare build containers from one shared script so CI and publication cannot
  install divergent toolchains.
- Check upstream version drift only in the scheduled update workflow; a new
  upstream release must not fail unrelated pull requests.
- Pin GitHub Actions to immutable commit SHAs and update them through Dependabot.
- Build with ephemeral keys, then sign with the protected release key using
  RSA/SHA-256 in a network-disabled container.
- Compare main with per-architecture deployed commit markers and publish only
  when release inputs change; use each marker again to verify Pages propagation
  before exact package installation tests.
