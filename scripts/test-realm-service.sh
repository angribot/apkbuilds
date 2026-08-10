#!/bin/sh
# Smoke-test the realm service subpackage after apk installation.
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
if output=$(realm -c /nonexistent/config.toml 2>&1); then
  echo "expected daemon to fail without a config; got:" >&2
  echo "$output" >&2
  exit 1
fi
echo "$output" | grep -q "config" || {
  echo "missing expected daemon error; got:" >&2
  echo "$output" >&2
  exit 1
}

# With a test config the daemon must bind the configured port.
mkdir -p /etc/realm
cat > /etc/realm/config.toml <<'EOF'
[[endpoints]]
listen = "127.0.0.1:18080"
remote = "127.0.0.1:9"
EOF
realm -c /etc/realm/config.toml &
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
