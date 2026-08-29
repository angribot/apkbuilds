#!/bin/sh
# Smoke-test cloudflared and its OpenRC service after apk installation.
# The service must reject the shipped comment-only configuration before it can
# attempt a tunnel connection.
#
# This smoke test does not test a real tunnel connection using credentials or
# an external Quick Tunnel: both require Cloudflare network access, neither of
# which belongs in package CI. The successful lifecycle check uses an
# operator-supplied test daemon shim instead.
set -eu

version=$1
service=/etc/init.d/cloudflared
config=/etc/cloudflared/config.yml
cloudflared --version | grep -F "$version" >/dev/null
cloudflared tunnel --help | grep -F "run" >/dev/null

test -x /usr/bin/cloudflared
test -f /usr/share/man/man1/cloudflared.1
test -d /var/lib/cloudflared
test -f "$config"
grep -F 'credentials-file:' "$config" >/dev/null
grep -F 'token-file:' "$config" >/dev/null
grep -F 'command_user=cloudflared:cloudflared' "$service" >/dev/null
grep -F 'command_args="tunnel --config /etc/cloudflared/config.yml run"' \
	"$service" >/dev/null

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

service_backup=$(mktemp)
config_backup=$(mktemp)
test_daemon=$(mktemp)
cp "$service" "$service_backup"
cp "$config" "$config_backup"
cleanup() {
	"$service" --nodeps stop >/dev/null 2>&1 || true
	cat "$service_backup" > "$service"
	cat "$config_backup" > "$config"
	rm -f "$service_backup" "$config_backup" "$test_daemon"
}
trap cleanup EXIT

cat > "$test_daemon" <<'EOF'
#!/bin/sh
while :; do
	sleep 1
done
EOF
chmod 755 "$test_daemon"
sed -i "s#^command=/usr/bin/cloudflared\$#command=$test_daemon#" "$service"

run_service_with_mode() {
	mode=$1
	printf '%s: /etc/cloudflared/test-credential\n' "$mode" > "$config"
	"$service" --nodeps start
	pid=$(cat /run/cloudflared.pid)
	kill -0 "$pid"
	expected_uid=$(id -u cloudflared)
	awk -v expected="$expected_uid" '
		$1 == "Uid:" { found = 1; if ($2 != expected) mismatch = 1 }
		END { exit !found || mismatch }
	' "/proc/$pid/status"
	"$service" --nodeps stop
}

run_service_with_mode credentials-file
run_service_with_mode token-file
