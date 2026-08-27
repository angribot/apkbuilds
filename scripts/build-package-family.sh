#!/bin/sh
# shellcheck disable=SC1091
# Build one package-origin family in the untrusted build container.
#
# The interface is deliberately explicit so the workflow only supplies paths
# and identities. The caller must provide a read-only source workspace, an
# ephemeral build environment, and a writable output directory.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: build-package-family.sh --arch ARCH --origin ORIGIN \
  --published URL --source-revision REVISION --workspace DIR --output DIR \
  --repository-key FILE --distfiles DIR --cargo-home DIR \
  --ccache-dir DIR --sccache-dir DIR [--force-build]
USAGE
}

arch=
origin=
published=
source_revision=
workspace=
output=
repository_key=
distfiles=
cargo_home=
ccache_dir=
sccache_dir=
force_build=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch|--origin|--published|--source-revision|--workspace|--output|\
    --repository-key|--distfiles|--cargo-home|--ccache-dir|--sccache-dir)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      case "$1" in
        --arch) arch=$2 ;;
        --origin) origin=$2 ;;
        --published) published=$2 ;;
        --source-revision) source_revision=$2 ;;
        --workspace) workspace=$2 ;;
        --output) output=$2 ;;
        --repository-key) repository_key=$2 ;;
        --distfiles) distfiles=$2 ;;
        --cargo-home) cargo_home=$2 ;;
        --ccache-dir) ccache_dir=$2 ;;
        --sccache-dir) sccache_dir=$2 ;;
      esac
      shift 2
      ;;
    --force-build)
      force_build=true
      shift
      ;;
    --help)
      usage >&1
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[ -n "$arch" ] && [ -n "$origin" ] && [ -n "$published" ] && \
  [ -n "$source_revision" ] && [ -n "$workspace" ] && [ -n "$output" ] && \
  [ -n "$repository_key" ] && [ -n "$distfiles" ] && [ -n "$cargo_home" ] && \
  [ -n "$ccache_dir" ] && [ -n "$sccache_dir" ] || {
  usage
  exit 2
}

stage=arguments
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::build stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  exit "$status"
}
trap failure EXIT

stage=source-copy
mkdir -p "$output/source"
cp -R "$workspace/packages/$origin" "$output/source/"

stage=toolchain
sh "$workspace/scripts/prepare-builder.sh" \
  "$output" "$distfiles" "$cargo_home" "$ccache_dir" "$sccache_dir" \
  "$output/source/$origin"
. "$workspace/scripts/lib.sh"

stage='published-index'
cp "$repository_key" /etc/apk/keys/
mkdir -p /tmp/published
wget -q -T 15 -t 2 \
  -O /tmp/published/APKINDEX.tar.gz \
  "$published/APKINDEX.tar.gz"
apk verify /tmp/published/APKINDEX.tar.gz
tar -xOzf /tmp/published/APKINDEX.tar.gz APKINDEX \
  > /tmp/published/APKINDEX

stage=build-plan
su builder -c "abuild-keygen -a -n"
cp /home/builder/.config/abuild/*.rsa.pub /etc/apk/keys/
supports_arch "$arch" "$workspace/packages/$origin/APKBUILD" || exit 0
assert_origin_directory "$workspace/packages/$origin"
expected="/tmp/expected-$origin"
published_packages="/tmp/published-$origin"
su builder -c \
  "cd \"$output/source/$origin\" && abuild listpkg" \
  > "$expected"
apkindex_origin_apks \
  /tmp/published/APKINDEX "$origin" > "$published_packages"
declared=$(apkbuild_declared_build "$workspace/packages/$origin")
versions="/tmp/published-versions-$origin"
apkindex_origin_versions \
  /tmp/published/APKINDEX "$origin" > "$versions"
published_builds=$(format_published_builds "$versions")
if ! package_sets_equal "$expected" "$published_packages"; then
  printf '::notice::%s package set mismatch: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds"
fi
if [ "$force_build" != true ] && package_sets_equal "$expected" "$published_packages"; then
  stage='published-family'
  published_apks="/tmp/published/$origin"
  mkdir -p "$published_apks"
  while IFS= read -r package; do
    downloaded="$published_apks/$package"
    wget -q -T 15 -t 2 -O "$downloaded" \
      "$published/$package"
    apk verify "$downloaded"
  done < "$expected"
  printf '==> %s package family already published: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds"
  exit 0
fi

if [ "$force_build" != true ] && grep -Fx "$declared" "$versions" >/dev/null; then
  stage=build-identity
  printf '::error::%s build mismatch: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds" >&2
  printf '%s %s already published with a different package set\n' \
    "$origin" "$declared" >&2
  exit 1
fi

stage=compile
build_started=$(date +%s)
if ! su builder -c \
  "cd \"$output/source/$origin\" && CARGO_HOME=\"$cargo_home\" SCCACHE_DIR=\"$sccache_dir\" RUSTC_WRAPPER=sccache REPODEST=\"$output/$origin\" abuild -r"; then
  printf '::error::build stage=compile arch=%s package-origin=%s declared-build=%s published-build(s)=%s\n' \
    "$arch" "$origin" "$declared" "$published_builds" >&2
  exit 1
fi
build_seconds=$(( $(date +%s) - build_started ))
built="$output/$origin/packages/$arch"
actual="/tmp/actual-$origin"
find "$built" -maxdepth 1 -type f -name '*.apk' \
  -exec basename {} \; > "$actual"
stage=family-check
if ! package_sets_equal "$expected" "$actual"; then
  printf '::error::build stage=family-check arch=%s package-origin=%s declared-build=%s published-build(s)=%s\n' \
    "$arch" "$origin" "$declared" "$published_builds" >&2
  diff -u "$expected" "$actual" >&2 || true
  exit 1
fi

stage=smoke
set -- apk add --allow-untrusted --repository "$built"
for package in "$built"/*.apk; do set -- "$@" "$package"; done
if ! "$@"; then
  printf '::error::build stage=install arch=%s package-origin=%s declared-build=%s published-build(s)=%s\n' \
    "$arch" "$origin" "$declared" "$published_builds" >&2
  exit 1
fi
case "$origin" in
  gnupg)
    "$workspace/scripts/test-package.sh" \
      "$(apkbuild_field pkgver "$workspace/packages/gnupg/APKBUILD")"
    ;;
  orbien) "$workspace/scripts/test-orbien.sh" ;;
  ports-box) "$workspace/scripts/test-ports-box-service.sh" ;;
  realm) "$workspace/scripts/test-realm-service.sh" ;;
  tirith)
    "$workspace/scripts/test-tirith.sh" \
      "$(apkbuild_field pkgver "$workspace/packages/tirith/APKBUILD")"
    ;;
esac

stage=output
candidate="$output/built/$arch/$origin"
mkdir -p "$candidate"
cp "$built"/*.apk "$candidate/"
metrics="$output/metrics/$arch/$origin"
mkdir -p "$metrics"
{
  printf 'origin=%s\n' "$origin"
  printf 'arch=%s\n' "$arch"
  printf 'declared_build=%s\n' "$declared"
  printf 'published_builds=%s\n' "$published_builds"
  printf 'build_seconds=%s\n' "$build_seconds"
  # shellcheck disable=SC2046
  set -- $(du -sb "$ccache_dir")
  printf 'ccache_size_bytes=%s\n' "$1"
  # shellcheck disable=SC2046
  set -- $(du -sb "$sccache_dir")
  printf 'sccache_size_bytes=%s\n' "$1"
  printf '%s\n' 'ccache_stats_begin'
  su builder -c 'ccache --show-stats' 2>&1 || true
  printf '%s\n' 'sccache_stats_begin'
  su builder -c 'sccache --show-stats' 2>&1 || true
} > "$metrics/build.txt"
