#!/bin/sh
# Validate candidate package families and merge them into a signed baseline.
# Runs before the repository signing key enters the isolated signer.
set -eux

pages=$1
built=$2
workspace=$3
repository_key=$4

# lib.sh is checked independently; its runtime path comes from the container mount.
# shellcheck source=/dev/null
. "$workspace/scripts/lib.sh"
cp "$repository_key" /etc/apk/keys/

for arch in x86_64 aarch64; do
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
    assert_origin_directory "$workspace/packages/$origin"
    declared=$(apkbuild_field pkgver \
      "$workspace/packages/$origin/APKBUILD")-r$(
      apkbuild_field pkgrel "$workspace/packages/$origin/APKBUILD"
    )
    candidate_index="$work/$origin-APKINDEX.tar.gz"
    apk index --no-warnings --quiet \
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
done
