# Build zerostack without relying on upstream release binaries

Build zerostack with Alpine's toolchain instead of repackaging upstream release
binaries. The source repository originally chose binary repackaging to keep
builds small, but an unusable v1.7.2 aarch64 binary forced that architecture to
remain on an older published build (issue #35). A source build costs more
compilation time and requires the Rust toolchain, but gives both
origin-supported architectures consistent package input under the source
repository's build and verification controls; upstream binaries should be
reintroduced only if their cross-architecture reliability outweighs
surrendering those controls.
