#!/bin/sh
# Require a package-origin build identity increase for every changed input.
# shellcheck disable=SC1091

set -eu
. scripts/lib.sh

status=0
for origin in $(all_origins); do
  apkbuild="packages/$origin/APKBUILD"
  git diff --quiet "$BASE_SHA" -- "packages/$origin" && continue
  previous="$RUNNER_TEMP/$origin-APKBUILD"
  git show "$BASE_SHA:$apkbuild" > "$previous" 2>/dev/null || continue
  old=$(apkbuild_field pkgver "$previous")-r$(apkbuild_field pkgrel "$previous")
  new=$(apkbuild_field pkgver "$apkbuild")-r$(apkbuild_field pkgrel "$apkbuild")
  if [ "$(apk version -t "$new" "$old")" != '>' ]; then
    echo "$origin must increase pkgver or pkgrel: $old -> $new" >&2
    status=1
  fi
done
exit "$status"
