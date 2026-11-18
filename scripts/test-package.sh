#!/bin/sh
set -eu
version=$1
version_output=$(gpg --version 2>&1)
printf '%s\n' "$version_output" | head -1 | grep -F "$version"
if printf '%s\n' "$version_output" | grep -Eqi 'development|beta|release candidate'; then
  echo 'unexpected development/beta/RC GnuPG warning' >&2
  exit 1
fi
work=$(mktemp -d)
cleanup() {
  # gpg autostarts gpg-agent and scdaemon with sockets in the homedir. They
  # unlink those sockets while exiting, which races rm -rf, and gpgconf --kill
  # returns before they exit, so wait up to five seconds for the sockets to go.
  gpgconf --homedir "$work" --kill all || true
  tries=50
  while ls "$work"/S.* >/dev/null 2>&1; do
    if [ "$tries" -eq 0 ]; then
      echo 'GnuPG daemon sockets remain after five seconds' >&2
      break
    fi
    sleep 0.1
    tries=$((tries - 1))
  done
  rm -rf "$work"
}
trap cleanup EXIT
gpg --batch --homedir "$work" --passphrase '' --quick-generate-key ci@example.invalid default default 1d
printf 'apkbuilds\n' > "$work/message"
gpg --batch --homedir "$work" --detach-sign "$work/message"
gpg --batch --homedir "$work" --verify "$work/message.sig" "$work/message"
