# Serialize package origin updates through one writer

The scheduled updater previously used a sequential matrix whose jobs all checked
out the same commit, so an earlier push could make later package origin updates
fail; run all updaters in one writer job, in a fixed order, committing and
pushing each eligible package origin before the next, with bounded
fetch/rebase/push retries and no force-push. The ordered updater manifest under
`packages/updaters` registers every package origin with its updater and updater
test; `-|-` explicitly marks an origin without update automation. The writer
validates this manifest before running any updater. This preserves successful
package origin updates independently while discarding failed or unpublished
changes at the package origin boundary; build jobs remain parallel per
architecture and package origin as described in ADR-0009.
