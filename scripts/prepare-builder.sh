#!/bin/sh
# Install the build toolchain and create the unprivileged abuild user.
# Shared by ci.yml and publish.yml so their dependency sets cannot drift.
# Runs as root inside an alpine container. Arguments are directories to hand
# to the builder user.
set -eu
apk add --no-cache alpine-sdk curl python3
adduser -D builder
addgroup builder abuild
mkdir -p /etc/doas.d
echo 'permit nopass builder as root' > /etc/doas.d/builder.conf
for directory in "$@"; do
  chown -R builder:builder "$directory"
done
