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
- Build pull requests only when package, smoke-test, or CI build inputs change;
  zerostack-only changes do not rebuild GnuPG.
- Keep update merging in the trusted default-branch workflow; merge only a
  bot-owned, single-APKBUILD PR at the exact SHA that passed read-only CI.
- Publish automatically only after successful CI for the current main SHA;
  serialize deployments so post-deployment verification is never cancelled.
- Build with ephemeral keys, then sign with the protected release key in a
  network-disabled container.
- Compare main with the deployed commit marker and publish only when release
  inputs change; use the marker again to verify Pages propagation before exact
  package installation tests.
