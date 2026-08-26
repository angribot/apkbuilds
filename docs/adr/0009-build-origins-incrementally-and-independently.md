# Build package origins incrementally and independently

Only package origins whose package inputs have changed since the last push to
main enter the build pipeline; every version-controlled file below an origin,
including patches and service init scripts, is a package input that must advance
the declared build (ADR-0001), while full and scheduled runs reconcile all
origins. Validation and planning share one checkout and job so validation
failures prevent a build matrix; each architecture and package-origin build
waits for that job. Builds restore the latest compatible compiler-cache
snapshot scoped by architecture, package origin, runner operating system, and
toolchain, then save a unique snapshot because GitHub Actions cache entries are
immutable. These choices keep ordinary runs incremental and parallel without
weakening published-build immutability (ADR-0001), signing isolation
(ADR-0002), or atomic package-family publication (ADR-0006).
