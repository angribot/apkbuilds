# Deepen CI operation modules around publication outcomes

CI calls three operation modules. Building accepts a package origin,
architecture, source revision, and published APK repository URL. Signing accepts
the staged publication inputs supplied by the runner. Verification accepts an
architecture and whether declared builds must be installed. The modules own
container execution, fixed mount points, writable ownership, temporary paths,
and candidate output layout; container-only scripts under `scripts/operations/`
are implementation rather than caller interfaces. This supersedes ADR-0013's
explicit-path interfaces.

Only source distfiles are cached. Compiler caches, cache and timing metrics,
forced builds, and project-authored retry branches are omitted so every declared
build follows one correctness path and every failed acquisition or verification
remains directly traceable to one operation.

The deeper interfaces preserve the trust seams in ADR-0002 and atomicity in
ADR-0006. Build containers receive the repository signing key's public half but
never its private half. Candidate families are validated and merged without
network access before the persistent repository signing key enters a separate
network-isolated signer. The private key is removed before the staged snapshot
is signature-checked, then architecture-specific jobs install every declared
build before publication.
