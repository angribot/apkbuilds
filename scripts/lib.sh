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

# Print "name=version-rrevision" for a package origin, the exact-version form
# `apk add` needs to prove the published repository serves this build.
#   apkbuild_pinned_spec <origin-directory>
apkbuild_pinned_spec() {
  _aps_name=$(apkbuild_field pkgname "$1/APKBUILD")
  _aps_version=$(apkbuild_field pkgver "$1/APKBUILD")
  _aps_revision=$(apkbuild_field pkgrel "$1/APKBUILD")
  printf '%s=%s-r%s\n' "$_aps_name" "$_aps_version" "$_aps_revision"
}

# Print the .apk filename this APKBUILD is expected to produce. The build job
# tests for this file in the published repository to decide whether the origin
# still needs building, so a wrong name means a package is silently rebuilt
# every run.
#   apkbuild_pinned_apk <origin-directory>
apkbuild_pinned_apk() {
  _apa_name=$(apkbuild_field pkgname "$1/APKBUILD")
  _apa_version=$(apkbuild_field pkgver "$1/APKBUILD")
  _apa_revision=$(apkbuild_field pkgrel "$1/APKBUILD")
  printf '%s-%s-r%s.apk\n' "$_apa_name" "$_apa_version" "$_apa_revision"
}
