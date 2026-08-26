#!/bin/sh
# shellcheck disable=SC1091
# Verify staged APK repository trees and install every declared build. The
# caller controls networking; CI runs this module with --network none, as it
# did before extraction.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: verify-repository.sh --pages DIR --workspace DIR --arch ARCH|all \
  --repository-key FILE [--install-declared-builds]
USAGE
}

pages=
workspace=
requested_arch=
repository_key=
install_declared_builds=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pages|--workspace|--arch|--repository-key)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      case "$1" in
        --pages) pages=$2 ;;
        --workspace) workspace=$2 ;;
        --arch) requested_arch=$2 ;;
        --repository-key) repository_key=$2 ;;
      esac
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

[ -n "$pages" ] && [ -n "$workspace" ] && \
  [ -n "$requested_arch" ] && [ -n "$repository_key" ] || {
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
  cp "$repository_key" /etc/apk/keys/apkbuilds.rsa.pub
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
  echo "/pages/edge" >> /etc/apk/repositories
  stage=index
  if ! apk_update_with_retry; then
    printf '::error::verify stage=index arch=%s package-origin=all declared-builds=all published-builds=unknown\n' \
      "$arch" >&2
    exit 1
  fi

  stage=install
  for origin in $(all_origins); do
    supports_arch "$arch" "$workspace/packages/$origin/APKBUILD" || continue
    declared=$(apkbuild_field pkgver \
      "$workspace/packages/$origin/APKBUILD")-r$(
      apkbuild_field pkgrel "$workspace/packages/$origin/APKBUILD"
    )
    versions="$work/published-versions-$origin"
    apkindex_origin_versions "$index" "$origin" > "$versions"
    published_builds=
    while IFS= read -r version; do
      [ -n "$published_builds" ] && published_builds="$published_builds "
      published_builds="$published_builds$version"
    done < "$versions"
    [ -n "$published_builds" ] || published_builds='<none>'
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
