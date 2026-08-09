# Alpine Package Publishing

Tracks selected upstream software releases and publishes trusted packages for
Alpine edge. Maintains precise package identity, architecture availability,
and trust boundaries from upstream release through publication.

## Packages

**Package origin**:
A packaging definition governed by one version and revision that may produce
one or more packages.
_Avoid_: Source package, package directory

**Package**:
A named installable unit produced by a package origin.
_Avoid_: Origin, APK

**APK**:
An architecture-specific installable artifact of a package at one build identity.
_Avoid_: Package, artifact

**Split package**:
One of multiple packages produced by the same package origin.

**Service subpackage**:
A split package providing an init script for a package's daemon, installed
when OpenRC is present.
_Avoid_: OpenRC package

**Package family**:
The complete APK set produced by one package origin at one package version and
revision for one architecture.
_Avoid_: Split package set, artifact set

**Metapackage**:
A package whose dependencies select a package suite rather than supplying its
main functionality directly.

## Versions

**Upstream release**:
A versioned software release published by an upstream project.

**Eligible upstream release**:
An upstream release satisfying the acceptance policy of a package origin.
_Avoid_: Latest release, stable release

**Package version**:
The upstream-derived version assigned to a package origin.
_Avoid_: Release

**Package revision**:
The packaging revision of a package version.
_Avoid_: Package release

**Build identity**:
The exact combination of package name, package version, and package revision.

**Declared build**:
The build identity currently declared by a package origin.
_Avoid_: Current version

**Published build**:
A build identity included in the APK repository for a specific architecture.

## Architectures

**Project-supported architecture**:
An architecture the publishing system can build and verify.

**Origin-supported architecture**:
A project-supported architecture accepted by a specific package origin.

**Available build**:
An architecture-specific published build clients can install.

## Repositories And Trust

**Source repository**:
The version-controlled source for package definitions and publishing automation.

**APK repository**:
The signed package collection exposed to Alpine clients.
_Avoid_: Repository, repo

**Repository snapshot**:
The signed indexes and exact physical APK set published together.

**Updater**:
Automation that selects and verifies an eligible upstream release, then updates
its package origin.
_Avoid_: Tracker

**Build key**:
An ephemeral key that marks APKs produced by an untrusted build environment.

**Repository signing key**:
The persistent key authorizing APKs and indexes in the APK repository.
_Avoid_: Release key, signing key

**Upstream release key**:
An OpenPGP key used to authenticate signed upstream releases.
_Avoid_: Signing key
