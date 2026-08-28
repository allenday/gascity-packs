# GitHub Docs-Impact Gate Design

## Goal

Dogfood a GitHub pull-request gate that prevents merging until a City TechDocs agent has evaluated documentation impact for the pull request's exact head revision.

## Scope

The GitHub pack owns the provider edge. A signed `pull_request` delivery is a hint, not authority: the handler derives a stable source key from the immutable repository ID, pull-request number, and head SHA, and records source work through the existing `gc bd` command seam.

That source work is assigned to a City TechDocs agent. The agent returns a signed-by-provenance, revision-bound review artifact containing a verdict, concise rationale, evidence paths, confidence, and an optional safe documentation patch. A trusted projector validates that artifact and only then creates one completed GitHub Check Run tied to the same SHA. GitHub is a projection surface, not the decision-maker.

No check is created while agent work is pending, unavailable, malformed, or inconclusive. The already-required check is therefore absent and GitHub blocks merge without publishing a fabricated decision.

## Boundaries

- No Gas City core changes and no Gitea adaptation.
- The worker binds only to loopback; Tailscale Funnel exposes only `/v0/github/webhook`.
- Delivery IDs are audit receipts only, never source-work identity.
- The webhook and worker never publish deterministic path classification, an in-progress check, a file inventory, or internal bead IDs to GitHub.
- Only an agent verdict of `no-impact` or `docs-sufficient` may produce a successful check conclusion. `docs-change-required`, `proposal-ready`, and `inconclusive` remain non-successful.
- The agent artifact is bound to repository ID, PR number, and full head SHA. A different revision can never inherit its verdict or patch.
- The GitHub check contains only the decision, a human-readable rationale, and one appropriate next action. The linked run page contains reviewed evidence and an optional patch; it does not expose City identifiers.
- Branch protection is enabled after a controlled advisory run proves pending, terminal, duplicate-delivery, and new-head behavior.

## Acceptance

1. One active source bead is reconciled per repository ID, PR number, and head SHA and is addressable by the TechDocs agent.
2. Before a valid TechDocs artifact exists, no GitHub check is published for that revision.
3. The projector rejects missing, malformed, untrusted, or identity-mismatched artifacts without publishing a decision.
4. A new head SHA cannot inherit a previous verdict or successful conclusion.
5. The visible check renders the agent's decision, rationale, and next action—without City IDs, raw SHA plumbing, or generic path-policy claims.
6. GitHub refuses merge while the required check is absent or non-successful.
7. Unit tests and three recorded dogfood PR runs cover `no-impact`, `docs-sufficient`, and `docs-change-required`/`proposal-ready` behavior.
