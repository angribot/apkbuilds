#!/bin/sh
# Validate candidate package families and merge them into a signed baseline.
# Runs before the repository signing key enters the isolated signer.
set -eux

arch=all
origin=all
stage=arguments
work=
failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '::error::merge stage=%s arch=%s package-origin=%s exit=%s\n' \
      "$stage" "$arch" "$origin" "$status" >&2
  fi
  [ -z "$work" ] || rm -rf "$work"
  exit "$status"
}
trap failure EXIT

pages=$1
built=$2
workspace=$3
repository_key=$4

# lib.sh is checked independently; its runtime path comes from the container mount.
# shellcheck source=/dev/null
. "$workspace/scripts/lib.sh"
cp "$repository_key" /etc/apk/keys/

for arch in x86_64 aarch64; do
  origin=all
  stage='baseline-signature'
  source="$built/$arch"
  apk_repository="$pages/edge/$arch"
  apk verify "$apk_repository/APKINDEX.tar.gz"
  apk verify "$apk_repository"/*.apk

  work=$(mktemp -d)
  baseline="$work/baseline-APKINDEX"
  tar -xOzf "$apk_repository/APKINDEX.tar.gz" APKINDEX > "$baseline"
  apkindex_apks "$baseline" > "$work/indexed"
  find "$apk_repository" -maxdepth 1 -type f -name "*.apk" \
    -exec basename {} \; > "$work/physical"
  package_sets_equal "$work/indexed" "$work/physical"
  if ! test -d "$source"; then
    rm -rf "$work"
    continue
  fi

  for family in "$source"/*; do
    test -d "$family" || continue
    origin=${family##*/}
    stage='candidate-validation'
    assert_origin_directory "$workspace/packages/$origin"
    declared=$(apkbuild_field pkgver \
      "$workspace/packages/$origin/APKBUILD")-r$(
      apkbuild_field pkgrel "$workspace/packages/$origin/APKBUILD"
    )
    candidate_index="$work/$origin-APKINDEX.tar.gz"
    # Candidates carry the untrusted build key's signature; only their
    # structure is validated here, never their authenticity. The repository
    # signing key re-signs them later and the final verification step checks
    # exactly that signature.
    apk index --no-warnings --quiet --allow-untrusted \
      --output "$candidate_index" \
      "$family"/*.apk
    tar -xOzf "$candidate_index" APKINDEX \
      > "$work/$origin-APKINDEX"
    apkindex_validate_family "$work/$origin-APKINDEX" \
      "$origin" "$declared" "$arch"
    apkindex_origin_apks \
      "$work/$origin-APKINDEX" "$origin" \
      > "$work/$origin-indexed"
    find "$family" -maxdepth 1 -type f -name "*.apk" \
      -exec basename {} \; > "$work/$origin-physical"
    package_sets_equal \
      "$work/$origin-indexed" "$work/$origin-physical"

    previous="$work/$origin-previous"
    stage='family-merge'
    apkindex_origin_apks "$baseline" "$origin" > "$previous"
    while IFS= read -r package; do
      test -f "$apk_repository/$package"
      rm -f "$apk_repository/$package"
    done < "$previous"
    for candidate in "$family"/*.apk; do
      package=${candidate##*/}
      test ! -e "$apk_repository/$package"
      cp "$candidate" "$apk_repository/"
    done
  done
  rm -rf "$work"
  work=
done
