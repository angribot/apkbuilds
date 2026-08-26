# Build package origins incrementally and independently

CI selects only package origins whose inputs changed since the last push to
`main`, while full and scheduled runs reconcile all origins; every input below
an origin must advance its declared build to preserve published-build
immutability (ADR-0001). Diff, range, revision, and explicit manual selections
must resolve to valid origins before matrix expansion, validation and planning
share one checkout and job, and compiler-cache snapshots remain scoped and
immutable per architecture, origin, runner, and toolchain. Scheduled and manual
reconciliation compares every declared package family with the published
snapshot; after an updater changes `main`, its publication dispatch has an
additional bounded reconciliation attempt if the initial dispatch fails, while
CI recovery retries only final branch publication failures.

## Consequences

Ordinary runs remain incremental and parallel without weakening signing
isolation (ADR-0002) or atomic package-family publication (ADR-0006); validation,
build, signing, and verification failures remain visible rather than being
silently retried.
