# GitHub Docs-Impact Gate Design

## Goal

Dogfood a GitHub pull-request gate that prevents merging until a Docs specialist has evaluated documentation impact for the pull request's exact head revision.

## Scope

The GitHub pack owns the provider edge. A signed `pull_request` delivery is a hint, not authority: the handler derives a stable source key from the immutable repository ID, pull-request number, and head SHA, records source work through the existing `gc bd` command seam, and invokes a configured docs-impact action. The action projects one of `no-impact`, `docs-update-proposed`, or `needs-human-decision` as a GitHub Check Run tied to the same SHA.

## Boundaries

- No Gas City core changes and no Gitea adaptation.
- The worker binds only to loopback; Tailscale Funnel exposes only `/v0/github/webhook`.
- Delivery IDs are audit receipts only, never source-work identity.
- Only `no-impact` and `docs-update-proposed` are successful check conclusions.
- Branch protection is enabled after a controlled advisory run proves pending, terminal, duplicate-delivery, and new-head behavior.

## Acceptance

1. One active source bead is reconciled per repository ID, PR number, and head SHA.
2. A new head SHA cannot inherit a previous successful conclusion.
3. The visible check records source-bead ID, head SHA, result kind, and evidence.
4. GitHub refuses merge while the required check is pending or non-successful.
5. Unit tests and a recorded dogfood run cover the delivered behavior.
