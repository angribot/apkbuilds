#!/bin/sh
# Require a package-origin build identity increase for every changed input.
# shellcheck disable=SC1091

set -eu
. scripts/lib.sh

git diff --name-only "$BASE_SHA" -- packages/ > "$RUNNER_TEMP/changed-files"
status=0
for origin in $(changed_origins "$RUNNER_TEMP/changed-files"); do
  apkbuild="packages/$origin/APKBUILD"
  if [ ! -f "$apkbuild" ]; then
    echo "$origin changed package inputs but has no APKBUILD" >&2
    status=1
    continue
  fi
  previous="$RUNNER_TEMP/$origin-APKBUILD"
  if ! git show "$BASE_SHA:$apkbuild" > "$previous" 2>/dev/null; then
    continue
  fi
  old=$(apkbuild_field pkgver "$previous")-r$(apkbuild_field pkgrel "$previous")
  new=$(apkbuild_field pkgver "$apkbuild")-r$(apkbuild_field pkgrel "$apkbuild")
  if [ "$(apk version -t "$new" "$old")" != '>' ]; then
    echo "$origin must increase pkgver or pkgrel: $old -> $new" >&2
    status=1
  fi
done
exit "$status"
