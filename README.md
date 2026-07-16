# Alpine GnuPG packages

Signed GnuPG packages tracking the latest stable upstream release for Alpine
Linux edge. Beta and release-candidate versions are excluded.

Supported architectures: `x86_64` and `aarch64`.

## Add the repository

Run as root:

```sh
wget -q https://angribot.github.io/apkbuilds/apkbuilds.rsa.pub \
  -O /etc/apk/keys/apkbuilds.rsa.pub
echo "https://angribot.github.io/apkbuilds/edge" >> /etc/apk/repositories
apk update
apk add gnupg
```

To upgrade an existing installation:

```sh
apk update
apk upgrade gnupg
```

The repository contains GnuPG's complete split-package set. The `gpg` package
provides the minimal OpenPGP command-line tools, while the `gnupg` metapackage
installs the full suite. Both come from the same APKBUILD and build. Runtime and
build dependencies continue to come from Alpine edge, so stable Alpine releases
are not supported.
