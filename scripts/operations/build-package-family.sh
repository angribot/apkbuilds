#!/bin/sh
# shellcheck disable=SC1091
# Build one package-origin family in the untrusted build container.
# The public operation module owns this script's paths and mounts.
set -eu

[ "$#" -eq 4 ] || {
  printf '%s\n' 'internal build operation requires ARCH ORIGIN PUBLISHED SOURCE_REVISION' >&2
  exit 2
}
arch=$1
origin=$2
published=$3
source_revision=$4
workspace=${APKBUILDS_WORKSPACE:-/workspace}
output=${APKBUILDS_OUTPUT:-/new}
repository_key=${APKBUILDS_REPOSITORY_KEY:-/keys/apkbuilds.rsa.pub}
distfiles=${APKBUILDS_DISTFILES:-/var/cache/distfiles}

stage=arguments
work=
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::build stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  [ -z "$work" ] || rm -rf "$work"
  exit "$status"
}
trap failure EXIT

stage=source-copy
# Keep the staged checkout's repository directory named `packages`. abuild
# places packages under REPODEST/<repository>/<arch>, where <repository> is
# derived from the APKBUILD's parent directory.
mkdir -p "$output/packages"
cp -R "$workspace/packages/$origin" "$output/packages/"

stage=toolchain
sh "$workspace/scripts/prepare-builder.sh" \
  "$output" "$distfiles" "$output/packages/$origin"
. "$workspace/scripts/lib.sh"

stage='published-index'
cp "$repository_key" /etc/apk/keys/
work=$(mktemp -d)
published_directory=$work/published
mkdir -p "$published_directory"
wget -q -T 15 -t 1 \
  -O "$published_directory/APKINDEX.tar.gz" \
  "$published/APKINDEX.tar.gz"
apk verify "$published_directory/APKINDEX.tar.gz"
tar -xOzf "$published_directory/APKINDEX.tar.gz" APKINDEX \
  > "$published_directory/APKINDEX"

stage=build-plan
su builder -c "abuild-keygen -a -n"
cp /home/builder/.config/abuild/*.rsa.pub /etc/apk/keys/
supports_arch "$arch" "$workspace/packages/$origin/APKBUILD" || exit 0
expected="$work/expected-$origin"
published_packages="$work/published-$origin"
su builder -c \
  "cd \"$output/packages/$origin\" && abuild listpkg" \
  > "$expected"
apkindex_origin_apks \
  "$published_directory/APKINDEX" "$origin" > "$published_packages"
declared=$(apkbuild_declared_build "$workspace/packages/$origin")
versions="$work/published-versions-$origin"
apkindex_origin_versions \
  "$published_directory/APKINDEX" "$origin" > "$versions"
published_builds=$(format_published_builds "$versions")
published_family_matches=false
if package_sets_equal "$expected" "$published_packages"; then
  published_family_matches=true
else
  printf '::notice::%s package set mismatch: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds"
fi
if [ "$published_family_matches" = true ]; then
  stage='published-family'
  published_apks="$published_directory/$origin"
  mkdir -p "$published_apks"
  while IFS= read -r package; do
    downloaded="$published_apks/$package"
    wget -q -T 15 -t 1 -O "$downloaded" \
      "$published/$package"
    apk verify "$downloaded"
  done < "$expected"
  printf '==> %s package family already published: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds"
  exit 0
fi

if grep -Fx "$declared" "$versions" >/dev/null; then
  stage=build-identity
  printf '::error::%s build mismatch: source revision=%s declared build=%s published build(s)=%s\n' \
    "$origin" "$source_revision" "$declared" "$published_builds" >&2
  printf '%s %s already published with a different package set\n' \
    "$origin" "$declared" >&2
  exit 1
fi

stage=compile
if ! su builder -c \
  "cd \"$output/packages/$origin\" && REPODEST=\"$output/$origin\" abuild -r"; then
  printf '::error::build stage=compile arch=%s package-origin=%s declared-build=%s published-build(s)=%s\n' \
    "$arch" "$origin" "$declared" "$published_builds" >&2
  exit 1
fi
built="$output/$origin/packages/$arch"
actual="$work/actual-$origin"
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
  cloudflared)
    "$workspace/scripts/test-cloudflared.sh" \
      "$(apkbuild_field pkgver "$workspace/packages/cloudflared/APKBUILD")"
    ;;
  tirith)
    "$workspace/scripts/test-tirith.sh" \
      "$(apkbuild_field pkgver "$workspace/packages/tirith/APKBUILD")"
    ;;
esac

stage=output
candidate="$output/built/$arch/$origin"
mkdir -p "$candidate"
cp "$built"/*.apk "$candidate/"
