# Architecture

What the workflows cannot state themselves. For how the pipeline runs, read
`.github/workflows/ci.yml`.

## Layout

```
packages/<origin>/APKBUILD    one origin per directory
keys/apkbuilds.rsa.pub        the public half of the release key
scripts/lib.sh                helpers sourced by ci.yml
scripts/update*.py            per-package upstream trackers
```

## Adding a package

Create `packages/<origin>/APKBUILD` and open a pull request. Nothing else
needs editing: `all_origins` discovers origins from the tree, so the build,
sign, and verify jobs pick the package up on their own.

Only two architectures are supported, `x86_64` and `aarch64`, because those
are the native GitHub-hosted runners. The matrices name them literally; there
is no third architecture to generalise for.

## Version discipline

The build job skips any origin whose `<name>-<pkgver>-r<pkgrel>.apk` already
exists in the published repository. An edit that changes a package without
raising `pkgver` or `pkgrel` therefore never reaches users. CI enforces this on
pull requests with `apk version -t` against the merge base.

Reset `pkgrel` to `0` when `pkgver` changes; otherwise increment it.

## Key boundary

Two keys, and the split is the point:

- The **build job** generates a throwaway key per run. It executes upstream
  build scripts, so it must never hold anything worth stealing.
- The **sign job** holds the release key, from the `release` environment, and
  runs `--network none`. It only splits, signs, and re-joins `.apk` files that
  the build job produced.

A separate step then verifies the signatures with only the public key, so a
signing bug cannot pass unnoticed.

## Publication

`gh-pages` holds the served repository. Each publication force-pushes one
orphan commit, so the branch never accumulates the history of every `.apk`
ever built, while unchanged packages persist as unchanged blobs.

Updaters commit straight to `main`. A package that fails to build is not
published and the previously served release stays live; `main` is then left
carrying a broken APKBUILD until it is fixed.

## Upstream trust

- Track stable upstream GnuPG rather than Alpine's LTS-only version policy,
  keeping Alpine edge's package split, build options, and patches to minimise
  divergence. Dependencies are not maintained here.
- Pin release-key fingerprints in code as well as checking in the upstream key,
  so replacing the key file alone cannot authorise a source.
- Package zerostack's upstream static musl binaries directly. Ignore draft,
  prerelease, incomplete, and non-`vX.Y.Z` releases, and never downgrade when
  the GitHub API returns an older complete release.
- Check upstream drift only in the scheduled workflow, so a new upstream
  release cannot fail an unrelated pull request.
- Use only Python and shell standard tooling; no project dependencies.
- Pin actions to immutable commit SHAs, updated through Dependabot.
