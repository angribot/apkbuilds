#!/bin/sh
# Update package origins one at a time, then publish their successful commits
# as one batch after every updater has had a chance to run.

set -u

if [ "$#" -ne 1 ]; then
  echo "usage: update-packages.sh UPDATER-MANIFEST" >&2
  exit 2
fi
updater_manifest=$1
if [ ! -f "$updater_manifest" ]; then
  echo "::error::updater manifest not found: $updater_manifest" >&2
  exit 1
fi

failures=0
has_updates=0

validate_updater_manifest() {
  if ! awk -F '|' '
    /^[[:space:]]*$/ || /^#/ { next }
    NF != 2 {
      printf "::error::invalid updater manifest line %d: expected package-origin|updater\n", NR
      invalid = 1
      next
    }
    $1 == "" {
      printf "::error::invalid updater manifest line %d: package origin is empty\n", NR
      invalid = 1
      next
    }
    seen[$1]++ {
      printf "::error::duplicate package origin %s in updater manifest\n", $1
      invalid = 1
    }
    END { exit invalid }
  ' "$updater_manifest" >&2; then
    return 1
  fi

  for _vum_apkbuild in packages/*/APKBUILD; do
    [ -f "$_vum_apkbuild" ] || continue
    _vum_origin=${_vum_apkbuild#packages/}
    _vum_origin=${_vum_origin%/APKBUILD}
    if ! awk -F '|' -v origin="$_vum_origin" \
        '$1 == origin { found = 1 } END { exit !found }' \
        "$updater_manifest"; then
      echo "::error::$_vum_origin is missing from updater manifest" >&2
      return 1
    fi
  done

  while IFS='|' read -r _vum_origin _vum_updater; do
    case "$_vum_origin" in
      ''|'#'*) continue ;;
    esac
    if [ ! -f "packages/$_vum_origin/APKBUILD" ]; then
      echo "::error::updater manifest origin $_vum_origin has no APKBUILD" >&2
      return 1
    fi
    if [ -z "$_vum_updater" ]; then
      echo "::error::$_vum_origin has no updater registration" >&2
      return 1
    fi
    if [ ! -f "$_vum_updater" ]; then
      echo "::error::$_vum_origin updater not found: $_vum_updater" >&2
      return 1
    fi
  done < "$updater_manifest"
}

# A failed updater or commit must leave its APKBUILD at the current commit.
discard_uncommitted_update() {
  git restore --staged --worktree -- "$1"
}

push_batch() {
  if git push origin HEAD:main; then
    return 0
  fi
  echo "::error::could not push updater batch to main" >&2
  return 1
}

process_update() {
  _pu_package_origin="$1"
  _pu_updater="$2"
  _pu_apkbuild="$3"
  _pu_version=

  echo "Checking $_pu_package_origin"
  if ! _pu_version=$(python3 "$_pu_updater"); then
    echo "::error::$_pu_package_origin updater failed; skipping this package origin" >&2
    if ! discard_uncommitted_update "$_pu_apkbuild"; then
      echo "::error::could not discard failed $_pu_package_origin update" >&2
      return 2
    fi
    return 1
  fi

  if git diff --quiet -- "$_pu_apkbuild"; then
    echo "$_pu_package_origin has no eligible update"
    return 0
  fi

  if ! git add -- "$_pu_apkbuild"; then
    echo "::error::could not stage $_pu_package_origin APKBUILD" >&2
    discard_uncommitted_update "$_pu_apkbuild" || true
    return 2
  fi
  if ! git commit -q -m "$_pu_package_origin: upgrade to $_pu_version"; then
    echo "::error::could not commit $_pu_package_origin update" >&2
    discard_uncommitted_update "$_pu_apkbuild" || true
    return 2
  fi

  has_updates=1
  return 0
}

validate_updater_manifest || exit 1

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

# Preserve manifest order: the updater is a single writer, so each origin's
# local commit is isolated before the next updater changes the checkout.
while IFS='|' read -r _main_package_origin _main_updater; do
  case "$_main_package_origin" in
    ''|'#'*) continue ;;
  esac

  if process_update \
    "$_main_package_origin" "$_main_updater" \
    "packages/$_main_package_origin/APKBUILD"; then
    continue
  else
    _main_status=$?
    failures=1
    if [ "$_main_status" -eq 2 ]; then
      break
    fi
  fi
done < "$updater_manifest"

if [ "$has_updates" -eq 1 ]; then
  if ! push_batch; then
    failures=1
  fi
fi
exit "$failures"
