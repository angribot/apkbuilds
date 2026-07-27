# Package zerostack upstream binaries

Package zerostack's upstream static musl binaries instead of maintaining a
source build. Accept only complete, non-draft, non-prerelease releases with
strict `vX.Y.Z` versions and the expected architecture assets; this keeps the
package pipeline small while deliberately trusting verified upstream binaries.
