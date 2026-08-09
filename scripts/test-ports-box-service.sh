#!/bin/sh
# Smoke-test the ports-box service subpackage in the container that just
# installed every built APK. Two assertions:
#   1. without a config, the service fails loudly (start_pre check)
#   2. with a test config, the service starts and binds the configured port
set -eu

apk add --no-cache openrc

# OpenRC's svc_lock needs /run/openrc; a container without init may
# lack it (post-install doesn't create it).
mkdir -p /run/openrc
ls -ld /run /run/openrc || true

# Without a config the init script's start_pre() must fail the start with a
# readable error before any daemon is launched.
if output=$(rc-service ports-box start 2>&1); then
  echo "expected start to fail without a config; got:" >&2
  echo "$output" >&2
  exit 1
fi
echo "$output" | grep -q "config /etc/ports-box/config.json not found" || {
  echo "missing expected startup error; got:" >&2
  echo "$output" >&2
  exit 1
}

# With a test config the service must start and bind the configured port.
mkdir -p /etc/ports-box
cat > /etc/ports-box/config.json <<'EOF'
{
  "api": { "listen": "127.0.0.1:17070" },
  "users": [
    { "name": "smoke", "rules": [ { "listen": "127.0.0.1:18080", "target": "127.0.0.1:9", "tag": "smoke" } ] }
  ]
}
EOF
rc-service ports-box start
sleep 1
rc-service ports-box status | grep -q started
# 18080 is 0x46A0 in the hex /proc/net/tcp local-address column.
awk 'NR>1 && $4=="0A" { split($2, a, ":"); if (a[2] == "46A0") found = 1 } END { exit !found }' /proc/net/tcp
rc-service ports-box stop
