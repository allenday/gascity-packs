# Durable GitHub Docs-Impact Lifecycle

## Goal

Make every opted-in pull request show a GitHub-visible Gas City check immediately, and ensure that check reaches a terminal, intelligible result even when the webhook process, City reviewer, or publisher restarts.

## Reader outcome

A pull-request author sees one `Gas City / docs-impact` check from receipt through completion. They never need to inspect City state to discover whether a review is queued, failed, or awaiting documentation work.

## Design

The durable docs-impact run is the source of truth. Its immutable identity is repository ID, PR number, and head SHA. It stores the GitHub Check Run ID, assignment digest, review deadline, terminal publication state, and the canonical review when available.

On an eligible webhook, intake validates the current head, atomically creates or loads that run, and creates the GitHub Check Run in `in_progress` before queuing City work. The initial Check summary says that Gas City is reviewing the exact revision and links to the opaque City run page. Intake returns without waiting for City.

A reconciler owns all asynchronous transitions. It scans non-terminal runs, verifies their PR head before every remote write, and performs one of these actions:

- requeue an unclaimed or expired immutable City assignment;
- validate and project a matching candidate;
- create a same-repository stacked follow-up PR for a safe `proposal-ready` result;
- complete the already-created GitHub Check Run;
- complete it as `action_required` with a concise operational reason when the deadline expires or an invalid candidate is final.

The reconciler must be idempotent: repeated scans adopt an existing Check Run by external ID and never create a second check or follow-up PR. A changed PR head neutralizes the old check and makes the old run terminal stale.

## Boundaries

- City sees only immutable, sanitized evidence and writes only its candidate file and bead state.
- The validator remains strict; the assignment includes a separate immutable proposal identity so a City proposal can satisfy the existing artifact schema without expanding the review identity.
- The trusted intake/reconciler is the only component with GitHub credentials or branch-write authority.
- Fork PRs and unavailable write authority remain proposal-only; their check still completes with a City-page link and a clear next action.
- The check does not embed a patch diff. The City page shows evidence and diff; a successful same-repository proposal links to the stacked follow-up PR.

## Failure semantics

`in_progress` is visible while the deadline has not elapsed. A City restart is recoverable: the same immutable assignment is requeued. An intake restart is recoverable: the reconciler resumes from durable state. On deadline expiry, the check completes `action_required`, explaining that City did not produce a validated review and linking to the run. No non-terminal run may be invisible on GitHub.

## Acceptance tests

1. A new PR receives one in-progress `Gas City / docs-impact` check before any City candidate exists.
2. A valid City review completes that exact check once, with the existing success/action-required semantics.
3. Restarting webhook, worker, and City after assignment creation still completes the original check after a matching candidate appears.
4. A stale head neutralizes the old check and cannot publish a result for the new head.
5. A safe same-repository proposal creates one stacked follow-up PR and the original check links to it.
6. An expired or invalid review completes visibly as action-required; it cannot leave a protected PR without a check.
