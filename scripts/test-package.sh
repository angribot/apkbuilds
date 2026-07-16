#!/bin/sh
set -eu
version=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
gpg --batch --homedir "$work" --passphrase '' --quick-generate-key ci@example.invalid default default 1d
printf 'apkbuilds\n' > "$work/message"
gpg --batch --homedir "$work" --detach-sign "$work/message"
gpg --batch --homedir "$work" --verify "$work/message.sig" "$work/message"
gpg --version | head -1 | grep -F "$version"
