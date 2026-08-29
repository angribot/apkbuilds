#!/bin/sh
# Sign a merged APK repository inside the network-isolated signer.
# The private key is available only at the fixed read-only mount supplied by
# the public signing module's network-isolated container.
set -eu

pages=${APKBUILDS_PAGES:-/pages}
repository_key=${APKBUILDS_REPOSITORY_KEY:-/keys/apkbuilds.rsa.pub}
private_key_file=${APKBUILDS_PRIVATE_KEY:-/private-key}

arch=all
origin=all
stage=arguments
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::sign stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  rm -f "$private_key"
  exit "$status"
}
trap failure EXIT

stage=key-setup
umask 077
private_key=${TMPDIR:-/tmp}/apkbuilds.rsa
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
