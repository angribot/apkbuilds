#!/bin/sh
# Build one package family behind the CI container seam.
set -eu

usage() {
  printf '%s\n' \
    'usage: build-package-family.sh --origin ORIGIN --arch ARCH --source-revision REVISION --published URL'
}

origin=
arch=
source_revision=
published=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --origin|--arch|--source-revision|--published)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$1" in
        --origin) origin=$2 ;;
        --arch) arch=$2 ;;
        --source-revision) source_revision=$2 ;;
        --published) published=$2 ;;
      esac
      shift 2
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

[ -n "$origin" ] && [ -n "$arch" ] && [ -n "$source_revision" ] && \
  [ -n "$published" ] || {
  usage >&2
  exit 2
}
case "$arch" in
  x86_64|aarch64) ;;
  *) usage >&2; exit 2 ;;
esac

workspace=${GITHUB_WORKSPACE:-$(CDPATH='' cd "$(dirname "$0")/.." && pwd)}
runner_temp=${RUNNER_TEMP:-}
[ -n "$runner_temp" ] || {
  printf '%s\n' 'RUNNER_TEMP is required' >&2
  exit 2
}
output=$runner_temp/new
distfiles=$workspace/.cache/distfiles
repository_key=$workspace/keys/apkbuilds.rsa.pub

stage=setup
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::build stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  exit "$status"
}
trap failure EXIT

mkdir -p "$output" "$distfiles"
stage=container
docker run --rm \
  -v "$workspace:/workspace:ro" \
  -v "$repository_key:/keys/apkbuilds.rsa.pub:ro" \
  -v "$output:/new" \
  -v "$distfiles:/var/cache/distfiles" \
  -w /workspace \
  alpine:edge \
    /workspace/scripts/operations/build-package-family.sh \
      --arch "$arch" \
      --origin "$origin" \
      --published "$published" \
      --source-revision "$source_revision" \
      --workspace /workspace \
      --output /new \
      --repository-key /keys/apkbuilds.rsa.pub \
      --distfiles /var/cache/distfiles

stage=outcome
candidate=$output/built/$arch/$origin
if [ -n "$(find "$candidate" -type f -name '*.apk' -print -quit 2>/dev/null)" ]; then
  built=true
else
  built=false
  printf 'no new packages for %s %s\n' "$arch" "$origin"
fi
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  printf 'built=%s\n' "$built" >> "$GITHUB_OUTPUT"
  printf 'artifact=%s\n' "$output/built" >> "$GITHUB_OUTPUT"
fi
