#!/bin/sh
# Update package origins one at a time so every successful commit reaches main
# before the next updater changes the checkout.

set -u

PUSH_ATTEMPTS=3
failures=0
fatal_failure=0

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
  return 0
}

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

# Keep this list in the order in which package origins are processed. Each
# entry is package origin|updater|APKBUILD and is deliberately independent.
while IFS='|' read -r _main_package_origin _main_updater _main_apkbuild; do
  if process_update \
    "$_main_package_origin" "$_main_updater" "$_main_apkbuild"; then
    continue
  else
    _main_status=$?
    failures=1
    if [ "$_main_status" -eq 2 ]; then
      fatal_failure=1
      break
    fi
  fi
done <<'UPDATES'
gnupg|scripts/update-gnupg.py|packages/gnupg/APKBUILD
zerostack|scripts/update-zerostack.py|packages/zerostack/APKBUILD
tirith|scripts/update-tirith.py|packages/tirith/APKBUILD
ports-box|scripts/update-ports-box.py|packages/ports-box/APKBUILD
orbien|scripts/update-orbien.py|packages/orbien/APKBUILD
realm|scripts/update-realm.py|packages/realm/APKBUILD
UPDATES

if [ "$fatal_failure" -eq 1 ]; then
  exit 1
fi
exit "$failures"
