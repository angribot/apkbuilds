# Domain Docs

This repo uses a single-context layout:
- `GLOSSARY.md` at the repo root.
- `docs/adr/` for architectural decisions.

## Before exploring

Read `GLOSSARY.md` and ADRs relevant to the area being explored.

If these files do not exist, proceed silently. Do not flag their
absence or suggest creating them upfront. The domain-modeling skill
creates them when terms or decisions are resolved.

## Use the glossary's vocabulary

Use defined domain terms in issue titles, proposals, hypotheses,
tests, and documentation. Avoid synonyms the glossary explicitly
rejects.

If a needed concept is missing, reconsider whether it belongs to
the domain or note the gap for domain-modeling.

## Flag ADR conflicts

Explicitly identify any proposal that contradicts an existing ADR
rather than silently overriding the decision.
