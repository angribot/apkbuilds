# Alpine packages

Signed packages that automatically track eligible upstream releases for Alpine
Linux edge. Each package origin defines whether it is built from source or uses
authenticated upstream binaries.

Project-supported architectures: `x86_64` and `aarch64`. Each package family
is published atomically per architecture. An origin-unsupported architecture
retains its previous available build.

## Add the APK repository

Run as root:

```sh
wget -q https://angribot.github.io/apkbuilds/apkbuilds.rsa.pub \
  -O /etc/apk/keys/apkbuilds.rsa.pub
echo "https://angribot.github.io/apkbuilds/edge" >> /etc/apk/repositories
apk update
apk add PACKAGE_NAME
```

To upgrade an existing installation:

```sh
apk update
apk upgrade PACKAGE_NAME
```

Package origins and package-specific files are maintained under
[`packages/`](packages/).

Runtime and build dependencies continue to come from Alpine edge, so stable
Alpine releases are not supported.
