#!/bin/sh
# Select package origins for a CI run and write its build matrix.
# shellcheck disable=SC1091

set -eu
. scripts/lib.sh

changed="$RUNNER_TEMP/changed-files"
changed_origins() {
  # Every file below an origin can change its package family, including
  # patches, init scripts, and other files referenced by APKBUILD.
  sed -n 's|^packages/\([^/]*\)/.*$|\1|p' "$changed" | sort -u
}

if [ "$EVENT" = "workflow_dispatch" ]; then
  if ! target_commit=$(git rev-parse "$REVISION^{commit}"); then
    printf '::error::invalid selected revision %s\n' "$REVISION" >&2
    exit 1
  fi
  if ! main_commit=$(git rev-parse "$MAIN_REVISION^{commit}"); then
    printf '::error::invalid main revision %s\n' "$MAIN_REVISION" >&2
    exit 1
  fi
  if ! git merge-base --is-ancestor "$target_commit" "$main_commit"; then
    printf '::error::selected revision %s is not on main\n' "$target_commit" >&2
    exit 1
  fi
fi

if [ "$EVENT" = "schedule" ] || [ "$FULL" = "true" ] || {
  [ "$EVENT" = "workflow_dispatch" ] &&
  [ "$EXPLICIT_REVISION" = "false" ] &&
  [ -z "$BASE_REVISION" ]
}; then
  # A manual run without a selected range is a reconciliation run. The
  # published snapshot may lag behind more than the current parent commit.
  origins=$(all_origins)
elif [ "$EVENT" = "pull_request" ]; then
  git diff --name-only "$BASE" -- packages/ > "$changed"
  origins=$(changed_origins)
elif [ "$EVENT" = "workflow_dispatch" ]; then
  if [ -n "$BASE_REVISION" ]; then
    if ! base_commit=$(git rev-parse "$BASE_REVISION^{commit}"); then
      printf '::error::invalid base revision %s\n' "$BASE_REVISION" >&2
      exit 1
    fi
  else
    if ! base_commit=$(git rev-parse "$REVISION^"); then
      printf '::error::selected revision %s has no valid parent\n' "$REVISION" >&2
      exit 1
    fi
  fi
  if ! git merge-base --is-ancestor "$base_commit" "$target_commit"; then
    printf '::error::base revision %s is not an ancestor of %s\n' \
      "$base_commit" "$target_commit" >&2
    exit 1
  fi
  git diff --name-only "$base_commit" "$target_commit" -- packages/ > "$changed"
  origins=$(changed_origins)
else
  git diff --name-only "$BEFORE" "$REVISION" -- packages/ > "$changed"
  origins=$(changed_origins)
fi

items=
for origin in $origins; do
  for arch in x86_64 aarch64; do
    runner=ubuntu-24.04
    [ "$arch" = aarch64 ] && runner=ubuntu-24.04-arm
    if supports_arch "$arch" "packages/$origin/APKBUILD"; then
      [ -n "$items" ] && items="$items,"
      items="$items{\"arch\":\"$arch\",\"origin\":\"$origin\",\"runner\":\"$runner\"}"
    fi
  done
done

if [ -z "$items" ]; then
  echo "has_origins=false" >> "$GITHUB_OUTPUT"
  echo 'matrix={"include":[]}' >> "$GITHUB_OUTPUT"
else
  echo "has_origins=true" >> "$GITHUB_OUTPUT"
  echo "matrix={\"include\":[$items]}" >> "$GITHUB_OUTPUT"
fi
