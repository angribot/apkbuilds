#!/bin/sh
# Smoke-test cloudflared and its OpenRC service after apk installation.
# The service must reject the shipped comment-only configuration before it can
# attempt a tunnel connection.
#
# This smoke test does not test a real tunnel connection: that requires
# operator credentials and Cloudflare network access, neither of which belong
# in package CI.
set -eu

version=$1
cloudflared --version | grep -F "$version" >/dev/null
cloudflared tunnel --help | grep -F "run" >/dev/null

test -x /usr/bin/cloudflared
test -f /usr/share/man/man1/cloudflared.1
test -f /etc/cloudflared/config.yml
grep -F 'credentials-file:' /etc/cloudflared/config.yml >/dev/null
grep -F 'token-file:' /etc/cloudflared/config.yml >/dev/null
grep -F 'command_user=cloudflared:cloudflared' /etc/init.d/cloudflared >/dev/null
grep -F 'command_args="tunnel --config /etc/cloudflared/config.yml run"' \
	/etc/conf.d/cloudflared >/dev/null
mkdir -p /run/openrc
: > /run/openrc/softlevel
if output=$(/etc/init.d/cloudflared --nodeps start 2>&1); then
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
