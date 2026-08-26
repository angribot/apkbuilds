# Protect main and gh-pages write paths

Protect the source repository's `main` branch with pull requests and the
stable `CI / gate` status check. Require administrators to follow the same
rules, reject force-pushes and deletions, and keep the required checks strict
so a branch is tested against the current `main` tip.

The package updater is the one deliberate `main` exception. It runs in the
trusted `Update packages` workflow and uses the `UPDATE_DEPLOY_KEY` deploy key
to bypass pull-request and status-check rules for each independently validated
package-origin commit. The publication job separately uses
`PAGES_DEPLOY_KEY` for its required orphan-snapshot force-push on `gh-pages`.
The private keys are exposed only to their respective jobs; the updater still
needs `actions: write` to dispatch CI, while publication uses no repository
`GITHUB_TOKEN` write permission.

GitHub repository rulesets expose deploy-key bypass as the `DeployKey` actor
type rather than allowing a particular deploy-key ID. This personal repository
therefore keeps exactly these two write deploy keys and scopes their private
secrets to the intended workflows. This is the strongest server-side exception
available without registering separate GitHub Apps; do not add another write
deploy key without reviewing both rulesets. The force-push itself remains
required by ADR-0003.

The protection configuration is repository settings rather than source-tree
state. Keep the following settings synchronized with this decision:

- `main`: the active `Protect main write path` ruleset requires a pull request,
  one approval, strict `CI / gate`, no force-push, and no deletion. Its
  `DeployKey` bypass is used by `UPDATE_DEPLOY_KEY` from `Update packages`.
- `gh-pages`: the active `Protect gh-pages write path` ruleset requires a pull
  request, one approval, no force-push, and no deletion. Its `DeployKey` bypass
  is used by `PAGES_DEPLOY_KEY` from `CI / publish`.
