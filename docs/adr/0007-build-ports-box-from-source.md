# Build ports-box from source

Build ports-box from its tagged source archive instead of shipping upstream's
release binaries. Upstream releases only glibc binaries (`x86_64-` /
`aarch64-unknown-linux-gnu`, built in a Debian container), which Alpine's musl
base cannot run without a glibc compatibility layer. A source build with
Alpine's Rust toolchain yields native musl binaries and follows the GnuPG
precedent of building in the package pipeline.

Accept only complete, non-draft, non-prerelease GitHub releases with strict
`vX.Y.Z` tags as eligible upstream releases. The source archive is fetched
over HTTPS from the tagged ref and pinned by sha512 in the package origin;
upstream publishes no signatures or archive digests, so HTTPS plus the pinned
checksum is the trust boundary, matching how source archives are handled
throughout Alpine packaging.
