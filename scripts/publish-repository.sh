#!/bin/sh
# Consume a verified staging snapshot and replace gh-pages with one orphan commit.
# PAGES_DEPLOY_KEY supplies publication authority; RUNNER_TEMP holds its temporary file.
set -eu

[ "$#" -eq 3 ] || {
  echo 'usage: publish-repository.sh SNAPSHOT SOURCE_REVISION REMOTE' >&2
  exit 2
}
snapshot=$1
revision=$2
remote=$3
stage=credentials
key=
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::publish stage=%s exit=%s\n' "$stage" "$status" >&2
  fi
  [ -z "$key" ] || rm -f "$key"
  exit "$status"
}
trap cleanup EXIT

umask 077
key=$(mktemp "${RUNNER_TEMP:?}/pages-deploy-key.XXXXXX")
[ -n "${PAGES_DEPLOY_KEY:-}" ] || {
  echo 'PAGES_DEPLOY_KEY is required' >&2
  exit 2
}
printf '%s\n' "$PAGES_DEPLOY_KEY" > "$key"
# Let Git's shell expand the quoted path, without shell-specific escaping.
PAGES_DEPLOY_KEY_FILE=$key
export PAGES_DEPLOY_KEY_FILE
# shellcheck disable=SC2016 # Expanded by Git's shell, not this one.
export GIT_SSH_COMMAND='ssh -i "$PAGES_DEPLOY_KEY_FILE" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
unset PAGES_DEPLOY_KEY

stage=snapshot
cd "$snapshot"
# Discard any Git metadata from the artifact, not just its previous history.
rm -rf .git
git init -q --initial-branch=gh-pages
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git remote add origin "$remote"
git add -A
stage=commit
git commit -q -m "Publish $revision"
stage=push
git push -q --force origin gh-pages
