#!/bin/sh
# Verify a staged repository snapshot behind the CI container seam.
set -eu

usage() {
  printf '%s\n' \
    'usage: verify-repository.sh --arch ARCH|all [--install-declared-builds]'
}

arch=
install_declared_builds=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      arch=$2
      shift 2
      ;;
    --install-declared-builds)
      install_declared_builds=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done
case "$arch" in
  x86_64|aarch64|all) ;;
  *) usage >&2; exit 2 ;;
esac

workspace=${GITHUB_WORKSPACE:-$(CDPATH='' cd "$(dirname "$0")/.." && pwd)}
runner_temp=${RUNNER_TEMP:-}
[ -n "$runner_temp" ] || {
  printf '%s\n' 'RUNNER_TEMP is required' >&2
  exit 2
}
pages=$runner_temp/pages
repository_key=$workspace/keys/apkbuilds.rsa.pub
origin=all
stage=container
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::verify stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  exit "$status"
}
trap failure EXIT

set -- docker run --rm
if [ "$install_declared_builds" != true ]; then
  set -- "$@" --network none
fi
set -- "$@" \
  -v "$pages:/pages:ro" \
  -v "$workspace:/workspace:ro" \
  -v "$repository_key:/keys/apkbuilds.rsa.pub:ro" \
  alpine:edge \
    /workspace/scripts/operations/verify-repository.sh \
      "$arch" "$install_declared_builds"
"$@"
