# Build package origins incrementally and independently

Only package origins whose package inputs have changed since the last push to
main enter the build pipeline; every version-controlled file below an origin,
including patches and service init scripts, is a package input that must advance
the declared build (ADR-0001), while full and scheduled runs reconcile all
origins. Planning runs independently from
repository checks, but each architecture and package-origin build waits for
both; builds restore the latest compatible compiler-cache snapshot scoped by
architecture, package origin, and runner operating system, then save a unique
snapshot because GitHub Actions cache entries are immutable. These choices
keep ordinary runs incremental and parallel without weakening published-build
immutability (ADR-0001), signing isolation (ADR-0002), or atomic package-family
publication (ADR-0006).
