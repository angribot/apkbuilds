#!/bin/sh
# Update package origins one at a time so every successful commit reaches main
# before the next updater changes the checkout.

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

PUSH_ATTEMPTS=3
DISPATCH_ATTEMPTS=3
failures=0
fatal_failure=0
has_updates=0
initial_commit=
final_commit=

validate_updater_manifest() {
  if ! awk -F '|' '
    /^[[:space:]]*$/ || /^#/ { next }
    NF != 3 {
      printf "::error::invalid updater manifest line %d: expected package-origin|updater|updater-test\n", NR
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

  while IFS='|' read -r _vum_origin _vum_updater _vum_test; do
    case "$_vum_origin" in
      ''|'#'*) continue ;;
    esac
    if [ ! -f "packages/$_vum_origin/APKBUILD" ]; then
      echo "::error::updater manifest origin $_vum_origin has no APKBUILD" >&2
      return 1
    fi
    if [ -z "$_vum_updater" ]; then
      echo "::error::$_vum_origin has no updater registration; use - for none" >&2
      return 1
    fi
    if [ "$_vum_updater" = "-" ]; then
      if [ "$_vum_test" != "-" ]; then
        echo "::error::$_vum_origin without an updater must register test as -" >&2
        return 1
      fi
      continue
    fi
    if [ ! -f "$_vum_updater" ]; then
      echo "::error::$_vum_origin updater not found: $_vum_updater" >&2
      return 1
    fi
    if [ -z "$_vum_test" ] || [ "$_vum_test" = "-" ]; then
      echo "::error::$_vum_origin updater has no test registration" >&2
      return 1
    fi
    if [ ! -f "$_vum_test" ]; then
      echo "::error::$_vum_origin updater test not found: $_vum_test" >&2
      return 1
    fi
  done < "$updater_manifest"
}

# Drop the current package origin commit after a failed push. Successful
# earlier package origins are already on origin/main, while the current one must
# not be carried into the next package origin's commit.
abandon_current_commit() {
  git rebase --abort >/dev/null 2>&1 || true
  git switch --detach --quiet origin/main
}

# A failed updater or commit must leave its APKBUILD at the current commit.
discard_uncommitted_update() {
  git restore --staged --worktree -- "$1"
}

push_commit() {
  _pc_package_origin="$1"

  for _pc_attempt in 1 2 3; do
    if git push origin HEAD:main; then
      return 0
    fi

    echo "$_pc_package_origin push attempt $_pc_attempt did not reach main; fetching origin/main"
    if ! git fetch origin main; then
      echo "$_pc_package_origin could not fetch origin/main after push failure" >&2
      continue
    fi

    # A network error can make a successful push look unsuccessful. Do not
    # rebase or retry a commit that is already present on the remote.
    if git merge-base --is-ancestor HEAD origin/main; then
      echo "$_pc_package_origin commit is already on origin/main"
      return 0
    fi

    if [ "$_pc_attempt" -lt "$PUSH_ATTEMPTS" ]; then
      echo "$_pc_package_origin rebasing onto origin/main"
      if ! git rebase origin/main; then
        echo "$_pc_package_origin could not rebase onto origin/main" >&2
        git rebase --abort >/dev/null 2>&1 || true
        return 1
      fi
    fi
  done

  echo "$_pc_package_origin push failed after $PUSH_ATTEMPTS attempts" >&2
  return 1
}

mark_publication_dispatch_failure() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo 'publication_dispatch_failed=true' >> "$GITHUB_OUTPUT"
  fi
}

dispatch_publication() {
  _dp_initial_commit="$1"
  _dp_final_commit="$2"

  _dp_attempt=1
  while [ "$_dp_attempt" -le "$DISPATCH_ATTEMPTS" ]; do
    if gh workflow run ci.yml --ref main \
        -f base_revision="$_dp_initial_commit" \
        -f revision="$_dp_final_commit" -f full=false; then
      return 0
    fi
    echo "CI publication dispatch attempt $_dp_attempt failed" >&2
    _dp_attempt=$((_dp_attempt + 1))
  done

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

  # Push each origin immediately. The next origin is not allowed to run with
  # an unpublished commit in the checkout.
  if ! push_commit "$_pu_package_origin"; then
    echo "::error::abandoning unpublished $_pu_package_origin update" >&2
    if ! abandon_current_commit; then
      echo "::error::could not restore checkout after $_pu_package_origin failure" >&2
      return 2
    fi
    return 1
  fi
  has_updates=1
  if ! final_commit=$(git rev-parse origin/main); then
    echo "::error::could not determine $_pu_package_origin update commit" >&2
    return 2
  fi
  return 0
}

validate_updater_manifest || exit 1

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
if ! initial_commit=$(git rev-parse HEAD); then
  echo "::error::could not determine the starting main commit" >&2
  exit 1
fi

# Preserve manifest order: the updater is a single writer, and each package
# origin reaches main before the next updater changes the checkout.
while IFS='|' read -r _main_package_origin _main_updater _main_test; do
  case "$_main_package_origin" in
    ''|'#'*) continue ;;
  esac
  if [ "$_main_updater" = "-" ]; then
    echo "$_main_package_origin has no updater; skipping"
    continue
  fi

  if process_update \
    "$_main_package_origin" "$_main_updater" \
    "packages/$_main_package_origin/APKBUILD"; then
    continue
  else
    _main_status=$?
    failures=1
    if [ "$_main_status" -eq 2 ]; then
      fatal_failure=1
      break
    fi
  fi
done < "$updater_manifest"

# A GITHUB_TOKEN push does not trigger another workflow. Dispatch one
# publication run after every package origin has had its chance to update, and
# pass the exact final revision while keeping main as the workflow ref.
if [ "$has_updates" -eq 1 ]; then
  if [ -z "$final_commit" ]; then
    echo "::error::could not dispatch CI publication without a main commit" >&2
    failures=1
  elif ! dispatch_publication "$initial_commit" "$final_commit"; then
    echo "::error::could not dispatch CI publication for $final_commit after $DISPATCH_ATTEMPTS attempts" >&2
    mark_publication_dispatch_failure
    failures=1
  fi
fi

if [ "$fatal_failure" -eq 1 ]; then
  exit 1
fi
exit "$failures"
