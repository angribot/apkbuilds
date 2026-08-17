# Build Tirith from source

Build Tirith from its tagged source archive for both origin-supported
architectures instead of mixing upstream artifacts with different libc and
provenance: upstream publishes an `aarch64` musl binary but only a glibc binary
for `x86_64`, while an Alpine source build produces consistent native musl
APKs. Accept only non-draft, non-prerelease GitHub releases with strict
`vX.Y.Z` tags, ignoring the separate `threatdb-*` release stream; pin each
HTTPS-fetched source archive by sha512 and build with the upstream Cargo
lockfile. Maintain Alpine package-manager detection as a downstream patch so
Tirith treats the APK as source-built, never reports its expected binary
difference as tampering, and delegates upgrades to APK.
