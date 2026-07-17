# Alpine packages

Signed GnuPG and zerostack packages automatically tracking stable upstream
releases for Alpine Linux edge. GnuPG is built from source; zerostack uses
upstream's static musl binaries.

Supported architectures: `x86_64` and `aarch64`.

## Add the repository

Run as root:

```sh
wget -q https://angribot.github.io/apkbuilds/apkbuilds.rsa.pub \
  -O /etc/apk/keys/apkbuilds.rsa.pub
echo "https://angribot.github.io/apkbuilds/edge" >> /etc/apk/repositories
apk update
apk add zerostack  # or: apk add gnupg
```

To upgrade an existing installation:

```sh
apk update
apk upgrade zerostack  # or: apk upgrade gnupg
```

The repository contains GnuPG's complete split-package set. The `gpg` package
provides the minimal OpenPGP command-line tools, while the `gnupg` metapackage
installs the full suite. The `zerostack` package installs the full upstream CLI.
Runtime and build dependencies continue to come from Alpine edge, so stable
Alpine releases are not supported.
