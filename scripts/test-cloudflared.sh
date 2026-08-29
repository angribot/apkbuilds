#!/bin/sh
# Smoke-test cloudflared and its OpenRC service after apk installation.
# The service must reject the shipped comment-only configuration before it can
# attempt a tunnel connection.
#
# This smoke test does not test a real tunnel connection using credentials or
# an external Quick Tunnel: both require Cloudflare network access, neither of
# which belongs in package CI. The successful lifecycle check uses a locally
# unreachable edge and a syntactically valid test token instead.
set -eu

version=$1
service=/etc/init.d/cloudflared
config=/etc/cloudflared/config.yml
token_file=/var/lib/cloudflared/smoke-token
cloudflared --version | grep -F "$version" >/dev/null
cloudflared tunnel --help | grep -F "run" >/dev/null

test -x /usr/bin/cloudflared

test -f /usr/share/man/man1/cloudflared.1 || \
	test -f /usr/share/man/man1/cloudflared.1.gz
test -d /var/lib/cloudflared
test -f "$config"
grep -F 'credentials-file:' "$config" >/dev/null
grep -F 'token-file:' "$config" >/dev/null
grep -F 'command_user=cloudflared:cloudflared' "$service" >/dev/null
grep -F 'command_args="tunnel --config /etc/cloudflared/config.yml run"' \
	"$service" >/dev/null
grep -F 'directory=/var/lib/cloudflared' "$service" >/dev/null

mkdir -p /run/openrc
: > /run/openrc/softlevel
if output=$("$service" --nodeps start 2>&1); then
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

config_backup=$(mktemp)
cp "$config" "$config_backup"
cleanup() {
	"$service" --nodeps stop >/dev/null 2>&1 || true
	cat "$config_backup" > "$config"
	rm -f "$config_backup" "$token_file"
}
trap cleanup EXIT

# This is a generated, syntactically valid token for a nonexistent tunnel.
# Pointing edge at an unreachable local port keeps the real daemon in its
# retry loop without contacting Cloudflare.
printf '%s\n' \
	'eyJhIjoidGVzdC1hY2NvdW50IiwicyI6ImMyVmpjbVYwIiwidCI6IjAwMDAwMDAwLTAwMDAtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSJ9' \
	> "$token_file"
chown cloudflared:cloudflared "$token_file"
chmod 600 "$token_file"
cat > "$config" <<EOF
no-autoupdate: true
no-prechecks: true
edge:
  - 127.0.0.1:9
token-file: $token_file
EOF

"$service" --nodeps start
sleep 1
pid=$(cat /run/cloudflared.pid)
kill -0 "$pid"
expected_uid=$(id -u cloudflared)
awk -v expected="$expected_uid" '
	$1 == "Uid:" { found = 1; if ($2 != expected) mismatch = 1 }
	END { exit !found || mismatch }
' "/proc/$pid/status"
test "$(readlink "/proc/$pid/cwd")" = /var/lib/cloudflared
cap_eff=$(awk '$1 == "CapEff:" { print $2 }' "/proc/$pid/status")
test "$cap_eff" = 0000000000000000
"$service" --nodeps stop
