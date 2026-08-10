#!/bin/sh
# Install the build toolchain and create the unprivileged abuild user.
# Sourced by the ci.yml build job so its toolchain stays in one place.
# Runs as root inside an alpine container. Arguments are directories to hand
# to the builder user.
set -eu
apk add --no-cache alpine-sdk ccache curl python3
adduser -D builder
addgroup builder abuild
mkdir -p /etc/doas.d
echo 'permit nopass builder as root' > /etc/doas.d/builder.conf
for directory in "$@"; do
  chown -R builder:builder "$directory"
done
# Write abuild user config to the XDG path (~/.config/abuild) so abuild
# sees it without an explicit ABUILD_USERDIR override.
mkdir -p /home/builder/.config/abuild
cat >> /home/builder/.config/abuild/abuild.conf <<'CCACHE'
USE_CCACHE=1
CCACHE_DIR=/home/builder/.cache/ccache
CCACHE
chown -R builder:builder /home/builder
