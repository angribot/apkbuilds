# Alpine packages

Signed packages that automatically track eligible upstream releases for Alpine
Linux edge. Each package origin defines whether it is built from source or uses
authenticated upstream binaries.

Project-supported architectures: `x86_64` and `aarch64`. Each package family
is published atomically per architecture. Published package origins cannot be
removed or narrowed to fewer architectures.

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

## Available packages

| Package origin | Installable packages | Description |
| --- | --- | --- |
| [`cloudflared`](packages/cloudflared/) | `cloudflared`, `cloudflared-doc`, `cloudflared-openrc` | Cloudflare Tunnel client |
| [`gnupg`](packages/gnupg/) | `gnupg`, `gnupg-doc`, `gnupg-lang`, `gnupg-dirmngr`, `gnupg-gpgconf`, `gnupg-scdaemon`, `gnupg-scdaemon-udev`, `gnupg-keyboxd`, `gnupg-wks-client`, `gpg`, `gpg-agent`, `gpg-wks-server`, `gpgsm`, `gpgv`, `gnupg-utils` | GNU Privacy Guard suite |
| [`orbien`](packages/orbien/) | `orbien`, `orbien-server`, `orbien-server-openrc` | Intranet tunneling client and server |
| [`ports-box`](packages/ports-box/) | `ports-box`, `ports-box-openrc` | TCP/UDP port forwarder with per-user traffic quotas |
| [`realm`](packages/realm/) | `realm`, `realm-openrc` | High-performance relay server |
| [`tirith`](packages/tirith/) | `tirith` | Terminal security for developers and AI agents |
| [`zerostack`](packages/zerostack/) | `zerostack` | Minimalistic coding agent |
