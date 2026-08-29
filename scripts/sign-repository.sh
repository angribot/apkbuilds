#!/bin/sh
# Merge complete candidate families and sign one staged repository snapshot.
set -eu

usage() {
  printf '%s\n' 'usage: sign-repository.sh'
}

case "${1:-}" in
  --help)
    usage
    exit 0
    ;;
  '') ;;
  *)
    usage >&2
    exit 2
    ;;
esac

workspace=${GITHUB_WORKSPACE:-$(CDPATH='' cd "$(dirname "$0")/.." && pwd)}
runner_temp=${RUNNER_TEMP:-}
[ -n "$runner_temp" ] || {
  printf '%s\n' 'RUNNER_TEMP is required' >&2
  exit 2
}
pages=$runner_temp/pages
built=$runner_temp/built
repository_key=$workspace/keys/apkbuilds.rsa.pub
private_key=
arch=all
origin=all
stage=candidates

failure() {
  status=$?
  [ -z "$private_key" ] || rm -f "$private_key"
  if [ "$status" -ne 0 ]; then
    printf '::error::sign stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  exit "$status"
}
trap failure EXIT

mkdir -p "$built"
if [ -z "$(find "$built" -type f -name '*.apk' -print -quit 2>/dev/null)" ]; then
  printf '%s\n' 'no candidate package families'
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s\n' 'snapshot_created=false' >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi
[ -n "${ABUILD_PRIVATE_KEY:-}" ] || {
  printf '%s\n' 'ABUILD_PRIVATE_KEY is required' >&2
  exit 2
}
private_key_contents=$ABUILD_PRIVATE_KEY
unset ABUILD_PRIVATE_KEY

stage=signer-image
docker build --tag apkbuilds-signer - <<'EOF'
FROM alpine:edge
RUN apk add --no-cache abuild
EOF

stage=family-merge
docker run --rm --network none \
  -v "$pages:/pages" \
  -v "$built:/built:ro" \
  -v "$workspace:/workspace:ro" \
  -v "$repository_key:/keys/apkbuilds.rsa.pub:ro" \
  apkbuilds-signer \
    /workspace/scripts/operations/merge-package-families.sh

stage=repository-signing
private_key=$runner_temp/repository-signing-key
umask 077
printf '%s\n' "$private_key_contents" > "$private_key"
unset private_key_contents
docker run --rm --network none \
  -v "$pages:/pages" \
  -v "$private_key:/private-key:ro" \
  -v "$repository_key:/keys/apkbuilds.rsa.pub:ro" \
  -v "$workspace/scripts/operations/sign-repository.sh:/sign-repository.sh:ro" \
  apkbuilds-signer \
    /sign-repository.sh
rm -f "$private_key"
private_key=

stage=signature-verification
sh "$workspace/scripts/verify-repository.sh" --arch all

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  printf '%s\n' 'snapshot_created=true' >> "$GITHUB_OUTPUT"
fi
