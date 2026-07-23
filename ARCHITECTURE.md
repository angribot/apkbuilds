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
- Assemble publication snapshots from release-key-verified unchanged APKs and new
  package outputs; replacements must increase their package version. Reset
  `pkgrel` to `0` when `pkgver` changes; otherwise increment `pkgrel`.
- Keep update merging in the trusted default-branch workflow; merge only a
  bot-owned, single-APKBUILD PR at the exact SHA that passed read-only CI.
- Dispatch read-only CI after merging an update whose exact head SHA passed CI;
  its successful `workflow_run` triggers publication. Manual publication is
  limited to first-release bootstrap. Serialize deployments so post-deployment
  verification is never cancelled.
- Pin GitHub Actions to immutable commit SHAs and update them through Dependabot.
- Build with ephemeral keys, then sign with the protected release key using
  RSA/SHA-256 in a network-disabled container.
- Compare main with the deployed commit marker and publish only when release
  inputs change; use the marker again to verify Pages propagation before exact
  package installation tests.
