# Publish updater results as one batch

The scheduled updater runs the registered updaters in manifest order through a
single writer. Every eligible package origin gets its own local commit, while a
failed updater is restored and does not prevent later updaters from running.
After all updaters have run, the writer makes at most one push of the successful
local commits. A run with no eligible updates makes no push. A failed push is
reported without project-authored retry, fetch, rebase, or publication-dispatch
paths; the next scheduled run can rediscover any successful commits that did
not reach `main`.

This replaces ADR-0011's per-origin remote-push decision. One batch gives the
push-triggered publication workflow one event and one CI run for all successful
updater results. The trade-off is that a failed batch push delays all of its
successful updates until the next scheduled run, rather than allowing a later
package origin to publish independently. Keeping each origin in a separate
local commit preserves reviewable history and lets a failed updater be isolated
without leaking changes into another origin.

The updater keeps manifest validation and the single-writer ordering from
ADR-0011. The push remains the only publication trigger; it does not dispatch CI
explicitly or retry a failed push.
