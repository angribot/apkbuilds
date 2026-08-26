#!/bin/sh
# Verify the repository rulesets that protect the two branch write paths.
# This is intentionally a read-only check; ruleset administration stays in
# GitHub repository settings, while this check makes drift visible.
set -eu

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
command -v gh >/dev/null 2>&1 || {
  echo '::error::gh is required to inspect repository rulesets' >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  echo '::error::jq is required to inspect repository rulesets' >&2
  exit 1
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rulesets="$work/rulesets.json"

# --slurp combines paginated JSON arrays before jq flattens them. The API
# response is kept in a file so every ruleset can be fetched and checked by ID.
if ! gh api --paginate --slurp \
  "repos/$GITHUB_REPOSITORY/rulesets?per_page=100" | jq 'add' > "$rulesets"; then
  echo '::error::could not list repository rulesets' >&2
  exit 1
fi

ruleset_id() {
  _vbr_name=$1
  _vbr_count=$(jq --arg name "$_vbr_name" \
    '[.[] | select(.name == $name and .target == "branch" and .enforcement == "active")] | length' \
    "$rulesets")
  if [ "$_vbr_count" -ne 1 ]; then
    echo "::error::expected exactly one active branch ruleset named $_vbr_name; found $_vbr_count" >&2
    return 1
  fi
  jq -r --arg name "$_vbr_name" \
    '.[] | select(.name == $name and .target == "branch" and .enforcement == "active") | .id' \
    "$rulesets"
}

check_ruleset() {
  _vbr_name=$1
  _vbr_ref=$2
  _vbr_require_status=$3
  _vbr_id=$(ruleset_id "$_vbr_name")
  _vbr_ruleset="$work/$_vbr_id.json"

  if ! gh api "repos/$GITHUB_REPOSITORY/rulesets/$_vbr_id" > "$_vbr_ruleset"; then
    echo "::error::could not read $_vbr_name ruleset" >&2
    return 1
  fi

  if ! jq -e \
    --arg ref "$_vbr_ref" \
    --arg require_status "$_vbr_require_status" '
      .enforcement == "active" and
      .target == "branch" and
      (.conditions.ref_name.include == [$ref]) and
      (.conditions.ref_name.exclude == []) and
      ([.rules[]?.type] | index("pull_request") != null) and
      ([.rules[]? | select(.type == "pull_request") |
        .parameters.required_approving_review_count] | index(1) != null) and
      ([.rules[]?.type] | index("non_fast_forward") != null) and
      ([.rules[]?.type] | index("deletion") != null) and
      ([.bypass_actors[]?] | length == 1) and
      ([.bypass_actors[]? |
        select(.actor_type == "DeployKey" and .bypass_mode == "always")] | length == 1) and
      (if $require_status == "true" then
        ([.rules[]? | select(.type == "required_status_checks") |
          select(.parameters.strict_required_status_checks_policy == true) |
          .parameters.required_status_checks[]?.context] |
          index("CI / gate") != null)
       else true end)
    ' "$_vbr_ruleset" >/dev/null; then
    echo "::error::$_vbr_name ruleset does not match the protected write-path policy" >&2
    return 1
  fi

  echo "verified $_vbr_name ruleset ($_vbr_id)"
}

check_ruleset 'Protect main write path' 'refs/heads/main' true
check_ruleset 'Protect gh-pages write path' 'refs/heads/gh-pages' false
