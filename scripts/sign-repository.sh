#!/bin/sh
# Sign a merged APK repository inside the network-isolated signer.
# ABUILD_PRIVATE_KEY is deliberately not accepted here; the caller passes a
# read-only private-key file that is mounted only into this container.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: sign-repository.sh --pages DIR --repository-key FILE \
  --private-key-file FILE
USAGE
}

pages=
repository_key=
private_key_file=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pages|--repository-key|--private-key-file)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      case "$1" in
        --pages) pages=$2 ;;
        --repository-key) repository_key=$2 ;;
        --private-key-file) private_key_file=$2 ;;
      esac
      shift 2
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

[ -n "$pages" ] && [ -n "$repository_key" ] && \
  [ -n "$private_key_file" ] || {
  usage
  exit 2
}

arch=all
origin=all
stage=arguments
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::sign stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  rm -f /tmp/apkbuilds.rsa
  exit "$status"
}
trap failure EXIT

stage=key-setup
umask 077
private_key=/tmp/apkbuilds.rsa
cp "$private_key_file" "$private_key"
cp "$repository_key" /etc/apk/keys/

stage='package-signing'
for sign_arch in x86_64 aarch64; do
  arch=$sign_arch
  stage='package-signing'
  apk_repository="$pages/edge/$arch"
  test -d "$apk_repository" || continue
  for package in "$apk_repository"/*.apk; do
    # Already-published packages carry a valid signature.
    apk verify "$package" && continue
    work=$(mktemp -d)
    (
      cd "$work"
      abuild-gzsplit < "$package"
      abuild-sign -q -t RSA256 \
        -k "$private_key" \
        -p "$repository_key" \
        control.tar.gz
      cat control.tar.gz data.tar.gz > "$package"
    )
    rm -rf "$work"
  done
  stage='index-signing'
  cd "$apk_repository"
  rm -f APKINDEX.tar.gz Packages.adb
  apk index --no-warnings --quiet \
    --output APKINDEX.tar.gz \
    --rewrite-arch "$arch" \
    ./*.apk
  abuild-sign -q -t RSA256 \
    -k "$private_key" \
    -p "$repository_key" \
    APKINDEX.tar.gz
done
