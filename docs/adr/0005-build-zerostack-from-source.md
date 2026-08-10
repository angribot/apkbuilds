# Build zerostack from source

Build zerostack from its tagged source archive instead of shipping upstream's
release binaries. We originally used upstream static musl binaries (to keep
the package pipeline small), but the v1.7.2 aarch64 binary was broken (issue
#35), so we switched to a source build with Alpine's Rust toolchain — the
same approach ports-box uses (ADR 0007). The HTTPS-fetched archive is pinned
by sha512; only non-draft, non-prerelease GitHub releases with strict
`vX.Y.Z` tags qualify as eligible upstream releases. Tests are disabled
(`!check`) because one test expects a git checkout but abuild extracts a
source tarball.
