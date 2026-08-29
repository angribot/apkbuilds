#!/bin/sh
# shellcheck disable=SC1091
# Verify staged APK repository trees and optionally install every declared
# build. The caller controls networking: CI runs signature-only verification
# offline and retains network access only for installation dependencies.
set -eu

[ "$#" -eq 2 ] || {
  printf '%s\n' 'internal verify operation requires ARCH INSTALL_DECLARED_BUILDS' >&2
  exit 2
}
requested_arch=$1
install_declared_builds=$2
case "$install_declared_builds" in
  true|false) ;;
  *) exit 2 ;;
esac

pages=${APKBUILDS_PAGES:-/pages}
workspace=${APKBUILDS_WORKSPACE:-/workspace}
repository_key=${APKBUILDS_REPOSITORY_KEY:-/keys/apkbuilds.rsa.pub}
key_directory=${APKBUILDS_KEY_DIRECTORY:-/etc/apk/keys}
repositories_file=${APKBUILDS_REPOSITORIES_FILE:-/etc/apk/repositories}

arch=all
origin=all
stage=arguments
work=
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::verify stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  [ -z "$work" ] || rm -rf "$work"
  exit "$status"
}
trap failure EXIT

. "$workspace/scripts/lib.sh"

verify_arch() {
  arch=$1
  origin=all
  apk_repository="$pages/edge/$arch"
  [ -d "$apk_repository" ] || return 0

  stage=signature
  mkdir -p "$key_directory"
  cp "$repository_key" "$key_directory/apkbuilds.rsa.pub"
  apk verify "$apk_repository/APKINDEX.tar.gz"
  apk verify "$apk_repository"/*.apk
  work=$(mktemp -d)
  index="$work/APKINDEX"
  tar -xOzf "$apk_repository/APKINDEX.tar.gz" APKINDEX > "$index"
  apkindex_apks "$index" > "$work/indexed"
  find "$apk_repository" -maxdepth 1 -type f -name '*.apk' \
    -exec basename {} \; > "$work/physical"
  package_sets_equal "$work/indexed" "$work/physical"

  if [ "$install_declared_builds" != true ]; then
    rm -rf "$work"
    work=
    return 0
  fi
  echo "/pages/edge" >> "$repositories_file"
  stage=index
  if ! apk update; then
    printf '::error::verify stage=index arch=%s package-origin=all declared-builds=all published-builds=unknown\n' \
      "$arch" >&2
    exit 1
  fi

  stage=install
  cd "$workspace"
  for origin in $(all_origins); do
    supports_arch "$arch" "$workspace/packages/$origin/APKBUILD" || continue
    declared=$(apkbuild_declared_build "$workspace/packages/$origin")
    versions="$work/published-versions-$origin"
    apkindex_origin_versions "$index" "$origin" > "$versions"
    published_builds=$(format_published_builds "$versions")
    spec=$(apkbuild_pinned_spec "$workspace/packages/$origin")
    apk_add_pinned_origin \
      "$arch" "$origin" "$declared" "$published_builds" "$spec"
  done
  rm -rf "$work"
  work=
}

case "$requested_arch" in
  all)
    verify_arch x86_64
    verify_arch aarch64
    ;;
  *) verify_arch "$requested_arch" ;;
esac
