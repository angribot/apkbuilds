#!/bin/sh
set -eu
version=$1
version_output=$(gpg --version 2>&1)
printf '%s\n' "$version_output" | head -1 | grep -F "$version"
if printf '%s\n' "$version_output" | grep -Eqi 'development|beta|release candidate|warning:.*(^|[^[:alnum:]_])rc([0-9._ -]|$)'; then
  echo 'unexpected development/beta/RC GnuPG warning' >&2
  exit 1
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
gpg --batch --homedir "$work" --passphrase '' --quick-generate-key ci@example.invalid default default 1d
printf 'apkbuilds\n' > "$work/message"
gpg --batch --homedir "$work" --detach-sign "$work/message"
gpg --batch --homedir "$work" --verify "$work/message.sig" "$work/message"
