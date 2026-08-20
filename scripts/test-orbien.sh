#!/bin/sh
set -eu

orbien --help | grep -F "orbien client" >/dev/null
test -f /usr/share/doc/orbien/orbien.toml
