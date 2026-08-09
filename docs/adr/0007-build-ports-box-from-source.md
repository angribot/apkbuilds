# Build ports-box from source

Build ports-box from its tagged source archive instead of shipping upstream's
release binaries: upstream only releases glibc binaries built in a Debian
container, which Alpine's musl base cannot run without a compatibility layer,
so a source build with Alpine's Rust toolchain yields native musl binaries.
Accept only non-draft, non-prerelease GitHub releases with strict `vX.Y.Z`
tags as eligible upstream releases; the HTTPS-fetched archive is pinned by
sha512 in the package origin, since upstream publishes no signatures or
archive digests, keeping the trust boundary at HTTPS plus the pinned
checksum.
