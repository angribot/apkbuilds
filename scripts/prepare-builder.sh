#!/bin/sh
# Install the build toolchain and create the unprivileged abuild user.
# Sourced by the ci.yml build job so its toolchain stays in one place.
# Runs as root inside an alpine container. Arguments are writable directories
# to hand to the builder user; never pass the source checkout here.
set -eu
apk add --no-cache alpine-sdk curl python3
adduser -D builder
addgroup builder abuild
mkdir -p /etc/doas.d
echo 'permit nopass builder as root' > /etc/doas.d/builder.conf
for directory in "$@"; do
  chown -R builder:builder "$directory"
done
chown -R builder:builder /home/builder
