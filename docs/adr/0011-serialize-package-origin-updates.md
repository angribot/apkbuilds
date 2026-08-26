# Serialize package origin updates through one writer

The scheduled updater previously used a sequential matrix whose jobs checked
out the same commit, so an earlier push could make a later package-origin
update fail; one writer now runs updaters in a fixed order and commits and
pushes each eligible origin before the next. The ordered updater manifest under
`packages/updaters` registers every package origin with its updater and updater
test, explicitly marks origins without update automation as `-|-`, and is
validated before any updater runs. This preserves successful package-origin
updates independently while discarding failed or unpublished changes at the
package-origin boundary; build jobs remain parallel per architecture and
package origin as described in ADR-0009.
