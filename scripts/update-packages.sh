#!/usr/bin/env bash
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
  local package_origin=$1
  local attempt

  for attempt in 1 2 3; do
    if git push origin HEAD:main; then
      return 0
    fi

    echo "$package_origin push attempt $attempt did not reach main; fetching origin/main"
    if ! git fetch origin main; then
      echo "$package_origin could not fetch origin/main after push failure" >&2
      continue
    fi

    # A network error can make a successful push look unsuccessful. Do not
    # rebase or retry a commit that is already present on the remote.
    if git merge-base --is-ancestor HEAD origin/main; then
      echo "$package_origin commit is already on origin/main"
      return 0
    fi

    if [ "$attempt" -lt "$PUSH_ATTEMPTS" ]; then
      echo "$package_origin rebasing onto origin/main"
      if ! git rebase origin/main; then
        echo "$package_origin could not rebase onto origin/main" >&2
        git rebase --abort >/dev/null 2>&1 || true
        return 1
      fi
    fi
  done

  echo "$package_origin push failed after $PUSH_ATTEMPTS attempts" >&2
  return 1
}

process_update() {
  local package_origin=$1
  local updater=$2
  local apkbuild=$3
  local version

  echo "Checking $package_origin"
  if ! version=$(python3 "$updater"); then
    echo "::error::$package_origin updater failed; skipping this package origin" >&2
    if ! discard_uncommitted_update "$apkbuild"; then
      echo "::error::could not discard failed $package_origin update" >&2
      return 2
    fi
    return 1
  fi

  if git diff --quiet -- "$apkbuild"; then
    echo "$package_origin has no eligible update"
    return 0
  fi

  if ! git add -- "$apkbuild"; then
    echo "::error::could not stage $package_origin APKBUILD" >&2
    discard_uncommitted_update "$apkbuild" || true
    return 2
  fi
  if ! git commit -q -m "$package_origin: upgrade to $version"; then
    echo "::error::could not commit $package_origin update" >&2
    discard_uncommitted_update "$apkbuild" || true
    return 2
  fi

  # Push each origin immediately. The next origin is not allowed to run with
  # an unpublished commit in the checkout.
  if ! push_commit "$package_origin"; then
    echo "::error::abandoning unpublished $package_origin update" >&2
    if ! abandon_current_commit; then
      echo "::error::could not restore checkout after $package_origin failure" >&2
      return 2
    fi
    return 1
  fi
  return 0
}

# Keep this list in the order in which package origins are processed. Each
# entry is package origin|updater|APKBUILD and is deliberately independent.
updates=(
  "gnupg|scripts/update-gnupg.py|packages/gnupg/APKBUILD"
  "zerostack|scripts/update-zerostack.py|packages/zerostack/APKBUILD"
  "tirith|scripts/update-tirith.py|packages/tirith/APKBUILD"
  "ports-box|scripts/update-ports-box.py|packages/ports-box/APKBUILD"
  "orbien|scripts/update-orbien.py|packages/orbien/APKBUILD"
  "realm|scripts/update-realm.py|packages/realm/APKBUILD"
)

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

for update in "${updates[@]}"; do
  IFS='|' read -r package_origin updater apkbuild <<< "$update"
  if process_update "$package_origin" "$updater" "$apkbuild"; then
    continue
  else
    status=$?
    failures=1
    if [ "$status" -eq 2 ]; then
      fatal_failure=1
      break
    fi
  fi
done

if [ "$fatal_failure" -eq 1 ]; then
  exit 1
fi
exit "$failures"
