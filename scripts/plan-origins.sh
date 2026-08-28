#!/bin/sh
# Select package origins for pull-request validation or main reconciliation.
# shellcheck disable=SC1091

set -eu
. scripts/lib.sh

changed="$RUNNER_TEMP/changed-files"
removed="$RUNNER_TEMP/removed-apkbuilds"
case "$EVENT" in
  pull_request)
    range_base=$BASE
    ;;
  push)
    range_base=$BEFORE
    ;;
  *)
    printf '::error::unsupported CI event %s\n' "$EVENT" >&2
    exit 1
    ;;
esac

git diff --no-renames --name-only "$range_base" "$REVISION" -- packages/ \
  > "$changed"
git diff --no-renames --diff-filter=D --name-only \
  "$range_base" "$REVISION" -- packages/ > "$removed"

status=0
while IFS= read -r path; do
  case "$path" in
    packages/*/APKBUILD)
      origin=${path#packages/}
      origin=${origin%%/*}
      printf '::error::removing package origin %s is unsupported\n' \
        "$origin" >&2
      status=1
      ;;
  esac
done < "$removed"
[ "$status" -eq 0 ] || exit "$status"

for origin in $(changed_origins "$changed"); do
  apkbuild="packages/$origin/APKBUILD"
  [ -f "$apkbuild" ] || continue
  previous="$RUNNER_TEMP/previous-$origin-APKBUILD"
  if ! git show "$range_base:$apkbuild" > "$previous" 2>/dev/null; then
    continue
  fi
  for arch in x86_64 aarch64; do
    if supports_arch "$arch" "$previous" && \
       ! supports_arch "$arch" "$apkbuild"; then
      printf '::error::removing architecture %s from package origin %s is unsupported\n' \
        "$arch" "$origin" >&2
      status=1
    fi
  done
done
[ "$status" -eq 0 ] || exit "$status"

if [ "$EVENT" = push ]; then
  origins=$(all_origins)
else
  origins=$(changed_origins "$changed")
fi

for origin in $origins; do
  if [ ! -f "packages/$origin/APKBUILD" ]; then
    printf '::error::selected package origin %s has no APKBUILD\n' \
      "$origin" >&2
    exit 1
  fi
  if ! assert_origin_directory "packages/$origin"; then
    printf '::error::selected package origin %s is invalid\n' "$origin" >&2
    exit 1
  fi
done

selected_origins=
for origin in $origins; do
  [ -n "$selected_origins" ] && selected_origins="$selected_origins "
  selected_origins="$selected_origins$origin"
done
printf 'origins=%s\n' "$selected_origins" >> "$GITHUB_OUTPUT"

matrix_items=
for origin in $origins; do
  for arch in x86_64 aarch64; do
    runner=ubuntu-24.04
    [ "$arch" = aarch64 ] && runner=ubuntu-24.04-arm
    if supports_arch "$arch" "packages/$origin/APKBUILD"; then
      [ -n "$matrix_items" ] && matrix_items="$matrix_items,"
      matrix_items="$matrix_items{\"arch\":\"$arch\",\"origin\":\"$origin\",\"runner\":\"$runner\"}"
    fi
  done
done

if [ -z "$matrix_items" ]; then
  echo "has_origins=false" >> "$GITHUB_OUTPUT"
  echo 'matrix={"include":[]}' >> "$GITHUB_OUTPUT"
else
  echo "has_origins=true" >> "$GITHUB_OUTPUT"
  echo "matrix={\"include\":[$matrix_items]}" >> "$GITHUB_OUTPUT"
fi
