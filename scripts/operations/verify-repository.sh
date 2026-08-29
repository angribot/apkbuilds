#!/bin/sh
# shellcheck disable=SC1091
# Verify staged APK repository trees and optionally install every declared
# build. The caller controls networking: CI runs signature-only verification
# offline and retains network access only for installation dependencies.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: operations/verify-repository.sh --arch ARCH|all \
  [--install-declared-builds]
USAGE
}

pages=${APKBUILDS_PAGES:-/pages}
workspace=${APKBUILDS_WORKSPACE:-/workspace}
requested_arch=
repository_key=${APKBUILDS_REPOSITORY_KEY:-/keys/apkbuilds.rsa.pub}
install_declared_builds=false
key_directory=${APKBUILDS_KEY_DIRECTORY:-/etc/apk/keys}
repositories_file=${APKBUILDS_REPOSITORIES_FILE:-/etc/apk/repositories}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      requested_arch=$2
      shift 2
      ;;
    --install-declared-builds)
      install_declared_builds=true
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

[ -n "$requested_arch" ] || {
  usage
  exit 2
}
case "$requested_arch" in
  x86_64|aarch64|all) ;;
  *) usage; exit 2 ;;
esac

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
