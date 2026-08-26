#!/bin/sh
# Shared helpers sourced by ci.yml. POSIX sh only: this runs inside alpine
# containers with busybox ash.

# Report whether an APKBUILD declares support for an architecture.
#   supports_arch <arch> <apkbuild-path>
# An absent or empty arch= line means "unrestricted", matching abuild's own
# default. A "!arch" exclusion wins over "all"/"noarch"/an explicit match,
# because abuild treats the negation as authoritative.
supports_arch() {
  _sa_arch=$1
  _sa_declared=$(apkbuild_field arch "$2")
  [ -z "$_sa_declared" ] && return 0
  case " $_sa_declared " in
    *" !$_sa_arch "*) return 1 ;;
    *" all "*|*" noarch "*|*" $_sa_arch "*) return 0 ;;
  esac
  return 1
}

# Print every package origin in the tree, one per line.
all_origins() {
  find packages -mindepth 2 -maxdepth 2 -name APKBUILD \
    -exec dirname {} \; | sed 's#^packages/##' | sort -u
}

# Print package origins named by changed package-input paths.
#   changed_origins <changed-files-path>
changed_origins() {
  sed -n 's|^packages/\([^/]*\)/.*$|\1|p' "$1" | sort -u
}

# Print a single top-level assignment's value from an APKBUILD, without
# executing the file. Accepts double-quoted, single-quoted, and bare values,
# all of which are legal in an APKBUILD, and strips the quotes. Only literal
# scalars are supported, which is all arch/pkgname/pkgver/pkgrel ever are.
#   apkbuild_field <field> <apkbuild-path>
apkbuild_field() {
  sed -n "s/^$1=\\(.*\\)\$/\\1/p" "$2" | head -n 1 | sed \
    -e 's/^"\(.*\)"$/\1/' \
    -e "s/^'\(.*\)'\$/\\1/"
}

# Require package-origin path name to equal APKBUILD pkgname. Alpine uses this
# name as package origin, so allowing them to drift makes family replacement
# ambiguous.
#   assert_origin_directory <origin-directory>
assert_origin_directory() {
  _aod_directory=${1%/}
  _aod_origin=${_aod_directory##*/}
  _aod_pkgname=$(apkbuild_field pkgname "$_aod_directory/APKBUILD")
  if [ "$_aod_origin" != "$_aod_pkgname" ]; then
    printf '%s must match pkgname %s\n' "$_aod_directory" "$_aod_pkgname" >&2
    return 1
  fi
}

# Print every APK filename from an extracted, signature-verified APKINDEX.
#   apkindex_apks <index-path>
apkindex_apks() {
  awk '
    BEGIN { RS = ""; FS = "\n" }
    {
      package = version = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^P:/) package = substr($i, 3)
        else if ($i ~ /^V:/) version = substr($i, 3)
      }
      if (package != "" && version != "") print package "-" version ".apk"
    }
  ' "$1"
}

# Print APK filenames belonging to a package origin from an extracted,
# signature-verified APKINDEX.
#   apkindex_origin_apks <index-path> <package-origin>
apkindex_origin_apks() {
  awk -v wanted="$2" '
    BEGIN { RS = ""; FS = "\n" }
    {
      package = version = origin = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^P:/) package = substr($i, 3)
        else if ($i ~ /^V:/) version = substr($i, 3)
        else if ($i ~ /^o:/) origin = substr($i, 3)
      }
      if (origin == wanted && package != "" && version != "")
        print package "-" version ".apk"
    }
  ' "$1"
}

# Print unique versions published for a package origin.
#   apkindex_origin_versions <index-path> <package-origin>
apkindex_origin_versions() {
  awk -v wanted="$2" '
    BEGIN { RS = ""; FS = "\n" }
    {
      version = origin = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^V:/) version = substr($i, 3)
        else if ($i ~ /^o:/) origin = substr($i, 3)
      }
      if (origin == wanted && version != "") versions[version] = 1
    }
    END { for (version in versions) print version }
  ' "$1"
}

# Validate every record in a candidate index as one complete package-origin
# family for the declared version and target architecture.
#   apkindex_validate_family <index-path> <origin> <version> <arch>
apkindex_validate_family() {
  awk -v wanted_origin="$2" -v wanted_version="$3" -v wanted_arch="$4" '
    BEGIN { RS = ""; FS = "\n" }
    {
      package = version = arch = origin = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^P:/) package = substr($i, 3)
        else if ($i ~ /^V:/) version = substr($i, 3)
        else if ($i ~ /^A:/) arch = substr($i, 3)
        else if ($i ~ /^o:/) origin = substr($i, 3)
      }
      count++
      if (package == "" || origin != wanted_origin || version != wanted_version ||
          (arch != wanted_arch && arch != "noarch")) invalid = 1
    }
    END { exit count == 0 || invalid }
  ' "$1"
}

# Compare newline-delimited package filename sets without depending on order.
#   package_sets_equal <expected-path> <actual-path>
package_sets_equal() {
  awk '
    NR == FNR { if ($0 != "") expected[$0]++; next }
    { if ($0 != "") actual[$0]++ }
    END {
      for (item in expected) if (expected[item] != actual[item]) exit 1
      for (item in actual) if (actual[item] != expected[item]) exit 1
    }
  ' "$1" "$2"
}

# Retry only APK index acquisition. Package resolution and installation are
# deliberately outside this loop because resolver failures are deterministic.
#   apk_update_with_retry
apk_update_with_retry() {
  _aur_delays=${APK_UPDATE_RETRY_DELAYS:-0 5 10 20 40 60}
  _aur_attempt=0
  for _aur_delay in $_aur_delays; do
    _aur_attempt=$((_aur_attempt + 1))
    [ "$_aur_delay" -eq 0 ] || sleep "$_aur_delay"
    if apk update; then
      return 0
    fi
    printf 'apk index retrieval attempt %s failed\n' "$_aur_attempt" >&2
  done
  return 1
}

# Install one exact package-origin build and log the identity on failure. This
# command is intentionally not part of apk_update_with_retry's retry loop.
#   apk_add_pinned_origin <arch> <origin> <declared-build> <published-builds> <spec>
apk_add_pinned_origin() {
  _apo_arch=$1
  _apo_origin=$2
  _apo_declared=$3
  _apo_published=$4
  _apo_spec=$5
  if apk add "$_apo_spec"; then
    return 0
  fi
  printf '::error::verify stage=install arch=%s package-origin=%s declared-build=%s published-build(s)=%s\n' \
    "$_apo_arch" "$_apo_origin" "$_apo_declared" "$_apo_published" >&2
  return 1
}

# Print "name=version-rrevision" for a package origin, the exact-version form
# `apk add` needs to prove the published APK repository serves this build.
#   apkbuild_pinned_spec <origin-directory>
apkbuild_pinned_spec() {
  _aps_name=$(apkbuild_field pkgname "$1/APKBUILD")
  _aps_version=$(apkbuild_field pkgver "$1/APKBUILD")
  _aps_revision=$(apkbuild_field pkgrel "$1/APKBUILD")
  printf '%s=%s-r%s\n' "$_aps_name" "$_aps_version" "$_aps_revision"
}
