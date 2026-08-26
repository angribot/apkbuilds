# Protect main and gh-pages write paths

GitHub rulesets protect the source repository's `main` branch with pull
requests, one approval, and the stable `CI / gate` status check, while both
protected branches reject deletion and non-fast-forward updates. The trusted
`Update packages` workflow bypasses `main` protection with `UPDATE_DEPLOY_KEY`,
and `CI / publish` bypasses `gh-pages` protection with `PAGES_DEPLOY_KEY`; the
private keys are exposed only to their respective jobs. Because GitHub exposes
deploy-key bypasses by actor type rather than deploy-key ID, the repository
keeps exactly these two write deploy keys and does not add another without
reviewing both rulesets.

## Consequences

Branch protection is repository settings rather than source-tree state, so
keep these settings synchronized with this decision:

- `main`: the active `Protect main write path` ruleset requires a pull request,
  one approval, strict `CI / gate`, no force-push, and no deletion. Its
  `DeployKey` bypass is used by `UPDATE_DEPLOY_KEY` from `Update packages`.
- `gh-pages`: the active `Protect gh-pages write path` ruleset requires a pull
  request, one approval, no force-push, and no deletion. Its `DeployKey` bypass
  is used by `PAGES_DEPLOY_KEY` from `CI / publish`.

The read-only `Verify branch protection` workflow runs weekly and on demand.
It uses `scripts/verify-branch-rulesets.sh` to check that both named rulesets
are active, target the intended branch, require the expected pull request and
status-check rules, reject deletion and non-fast-forward updates, and retain
only the documented deploy-key bypass. A failed check makes settings drift
visible without granting the workflow permission to change repository rules.
The force-push on `gh-pages` remains required by ADR-0003.
