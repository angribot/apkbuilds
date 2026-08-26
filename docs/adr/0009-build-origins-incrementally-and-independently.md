# Build package origins incrementally and independently

Only package origins whose package inputs have changed since the last push to
main enter the build pipeline; the rest are skipped without fetching the
published APKINDEX because unchanged package origins need no new family.
Every version-controlled file below an origin is a package input, including
patches and service init scripts. Each (architecture, package origin) pair runs
as an independent CI job, while persistent source-distfile and C/C++ caches
keep builds incremental; a periodic full rebuild catches drift that change
detection misses, such as a toolchain upgrade in alpine:edge.

A full iteration over all origins — downloading the published index,
verifying every already-published APK, and comparing package-family sets —
grows linearly with the number of package origins. Skipping published
families avoids redundant compilation but does not avoid the per-origin
overhead. Per-origin parallelism was deferred in the initial build pipeline
because there were only two package origins; with three and growing, one
slow source build delays everything else on its architecture. Builds already
run in throwaway containers with no persistent cache, so every rebuild of a
C or C++ origin (e.g. GnuPG) repeats the full configure-make cycle.

Change-driven scope, per-origin parallelism, and caching remove all three
bottlenecks without weakening existing invariants: published builds remain
immutable (ADR-0001), the repository signing key is still isolated from
builds (ADR-0002), and package families are still published atomically
(ADR-0006) because merge and signing stay centralized after all build jobs
complete.
