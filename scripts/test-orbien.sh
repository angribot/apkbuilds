#!/bin/sh
# Smoke-test the Orbien client and server packages after apk installation.
# The daemon must fail without its operator-supplied config and start with a
# minimal live config at the fixed path expected by the OpenRC service.
set -eu

orbien --help | grep -F "orbien client" >/dev/null
orbien-server --help | grep -F "orbien server" >/dev/null
test -f /usr/share/doc/orbien/orbien.toml
test -f /usr/share/doc/orbien/orbien-full.toml
test -f /usr/share/doc/orbien-server/orbien-server.toml
test -f /usr/share/doc/orbien-server/orbien-server-full.toml
test ! -e /etc/orbien/orbien-server.toml
grep -F 'command_user="root:root"' /etc/init.d/orbien-server >/dev/null
grep -F 'command_args="-c /etc/orbien/orbien-server.toml"' \
	/etc/init.d/orbien-server >/dev/null

mkdir -p /run/openrc
: > /run/openrc/softlevel
if output=$(/etc/init.d/orbien-server --nodeps start 2>&1); then
	echo "expected service to fail without a config; got:" >&2
	echo "$output" >&2
	exit 1
fi
echo "$output" | grep -F \
	"orbien server config /etc/orbien/orbien-server.toml not found" >/dev/null || {
	echo "missing expected service config error; got:" >&2
	echo "$output" >&2
	exit 1
}

mkdir -p /etc/orbien
cat > /etc/orbien/orbien-server.toml <<'EOF'
listen = "127.0.0.1:19527"
EOF
/etc/init.d/orbien-server --nodeps start
trap '/etc/init.d/orbien-server --nodeps stop >/dev/null 2>&1 || true' EXIT
sleep 1

pid=$(cat /run/orbien-server.pid)
kill -0 "$pid" || {
	echo "orbien-server service exited prematurely" >&2
	exit 1
}
# 19527 is 0x4C47 in the /proc/net/tcp local-address column.
awk 'NR > 1 && $4 == "0A" { split($2, a, ":"); if (a[2] == "4C47") found = 1 } END { exit !found }' \
	/proc/net/tcp

/etc/init.d/orbien-server --nodeps stop
trap - EXIT
