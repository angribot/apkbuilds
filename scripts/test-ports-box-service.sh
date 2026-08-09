#!/bin/sh
# Smoke-test the ports-box service subpackage after apk installation.
# Two assertions:
#   1. without a config, the daemon fails loudly
#   2. with a test config, the daemon starts and binds the configured port
#
# rc-service is not used: openrc 0.63 refuses to start services in a
# container that wasn't booted by openrc (requires softlevel + writable
# cgroup). The initd script is structurally verified by abuild's initdcheck
# and shellcheck; this test verifies the daemon binary works.
set -eu

# Without a config the daemon must fail cleanly with a readable error.
if output=$(ports-box -c /nonexistent/config.json -d /nonexistent 2>&1); then
  echo "expected daemon to fail without a config; got:" >&2
  echo "$output" >&2
  exit 1
fi
echo "$output" | grep -q "cannot read config" || {
  echo "missing expected daemon error; got:" >&2
  echo "$output" >&2
  exit 1
}

# With a test config the daemon must bind the configured port.
mkdir -p /etc/ports-box
cat > /etc/ports-box/config.json <<'EOF'
{
  "api": { "listen": "127.0.0.1:17070" },
  "users": [
    { "name": "smoke", "rules": [ { "listen": "127.0.0.1:18080", "target": "127.0.0.1:9", "tag": "smoke" } ] }
  ]
}
EOF
ports-box -c /etc/ports-box/config.json -d /var/lib/ports-box &
pid=$!
sleep 1

# Verify the daemon is still alive.
kill -0 "$pid" || {
  echo "daemon exited prematurely" >&2
  exit 1
}

# 18080 is 0x46A0 in the hex /proc/net/tcp local-address column.
awk 'NR>1 && $4=="0A" { split($2, a, ":"); if (a[2] == "46A0") found = 1 } END { exit !found }' /proc/net/tcp

kill "$pid"
wait "$pid" || true
