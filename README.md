# Alpine GnuPG packages

Signed GnuPG packages tracking the latest stable upstream release for Alpine
Linux edge. Beta and release-candidate versions are excluded.

Supported architectures: `x86_64` and `aarch64`.

## Add the repository

Run as root:

```sh
wget -q https://angribot.github.io/apkbuilds/apkbuilds.rsa.pub \
  -O /etc/apk/keys/apkbuilds.rsa.pub
echo "https://angribot.github.io/apkbuilds/$(apk --print-arch)" \
  >> /etc/apk/repositories
apk update
apk add gnupg
```

To upgrade an existing installation:

```sh
apk update
apk upgrade gnupg
```

The repository contains GnuPG's complete split-package set. Runtime and build
dependencies continue to come from Alpine edge, so stable Alpine releases are
not supported.

Release assets containing each architecture's repository are also available on
the [GitHub Releases](https://github.com/angribot/apkbuilds/releases) page.
