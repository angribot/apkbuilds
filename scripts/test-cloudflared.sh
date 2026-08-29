#!/bin/sh
# Smoke-test cloudflared and its OpenRC service inputs after apk installation.
# The OpenRC preflight hook must reject the shipped comment-only configuration.
#
# This smoke test does not test a real tunnel connection using credentials or
# an external Quick Tunnel: both require Cloudflare network access, neither of
# which belongs in package CI.
set -eu

version=$1
service=/etc/init.d/cloudflared
config=/etc/cloudflared/config.yml
cloudflared --version | grep -F "$version" >/dev/null
cloudflared tunnel --help | grep -F "run" >/dev/null

test -x /usr/bin/cloudflared
test -f /usr/share/man/man1/cloudflared.1 || \
	test -f /usr/share/man/man1/cloudflared.1.gz
test -d /var/lib/cloudflared
test -f "$config"
test -x "$service"
grep -F 'credentials-file:' "$config" >/dev/null
grep -F 'token-file:' "$config" >/dev/null
grep -F 'command_user=cloudflared:cloudflared' "$service" >/dev/null
grep -F 'command_args="tunnel --config /etc/cloudflared/config.yml run"' \
	"$service" >/dev/null

# Call the packaged preflight hook directly so this test does not require a
# booted OpenRC instance or writable cgroups in the package build container.
if output=$(sh -c '
	eerror() { printf "%s\n" "$*" >&2; }
	. "$1"
	start_pre
' sh "$service" 2>&1); then
	echo "expected the service to fail without operator configuration; got:" >&2
	echo "$output" >&2
	exit 1
fi
echo "$output" | grep -F \
	"cloudflared configuration /etc/cloudflared/config.yml must define credentials-file or token-file" \
	>/dev/null || {
	echo "missing expected cloudflared configuration error; got:" >&2
	echo "$output" >&2
	exit 1
}
