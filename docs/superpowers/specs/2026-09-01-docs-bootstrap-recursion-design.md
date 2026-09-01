# Bounded Documentation Bootstrap Design

## Outcome

An owner can explicitly start a documentation-baseline run for one GitHub
repository. The run uses the existing TechDocs/docs-impact decision as its
only documentation-analysis unit, projects selected bounded gaps into linked
GitHub issues and City beads, and stops with a durable, human-readable root
state.

This is additive to PR review. A normal `Gas City / docs-impact` pull-request
check never starts or expands bootstrap work.

## Authority and boundaries

The GitHub pack owns authenticated GitHub projection through its existing App
commands. The controller may create an App-owned issue, comment, branch, or
documentation PR only after the root admission and an exact, persisted
docs-impact result authorize that operation. It never writes to an author's
branch and never merges.

The TechDocs skill decides whether a concrete evidence surface needs docs. IDD
provides planning, issue lifecycle, critique, CI, acceptance, and closure
discipline. The bootstrap controller only carries provenance, evaluates
mechanical admission rules, persists actions before side effects, and
reconciles them.

## Durable model

Each root has an immutable logical identity:

`github-docs-bootstrap:<repository_id>:<root_issue_number>:<default_branch_sha>`

The persisted root record includes repository and installation identity, root
issue URL, default branch ref/SHA, configured budgets, current counters,
visited evidence-surface keys, terminal state, and child records. A child key
is the SHA-256 digest of the root identity plus the canonical docs-impact
decision identity and normalized evidence-surface paths. Replays therefore
adopt existing records rather than create duplicate issues, beads, or PRs.

Every child carries `root_issue_url`, `parent_issue_url`, `depth`,
`bootstrap_identity`, `snapshot_sha`, and the decision digest. A child may be
admitted only if all are present and match the persisted root snapshot.

## Admission and expansion

The only entrypoint is an explicit root request on a GitHub Issue, routed to a
new `docs-bootstrap` formula. It snapshots the default branch before any
analysis and records an initial root status comment.

A result may create one child only when it is a validated, exact
`docs-change-required` decision for that snapshot, the evidence surface was
not previously visited, all budgets remain available, and the decision has no
product ambiguity. The controller creates the GitHub child issue and City
bead idempotently, then assigns the docs-bootstrap worker. The worker follows
vendored TechDocs and IDD, creates an App-owned documentation branch/PR, and
reports its result to the child issue.

`no-impact` and `docs-sufficient` consume no child budget. `inconclusive`,
unsupported evidence, an incompatible snapshot, or product ambiguity do not
retry autonomously; they set the appropriate root terminal/escalation state.

## Guardrails

Defaults are deliberately small and must be explicit in the root record:

- maximum depth: `2`;
- maximum admitted children: `8`;
- maximum documentation PRs: `4`;
- maximum elapsed run time: `24h`;
- maximum consecutive non-progress reconciliations: `3`.

Budget checks occur before persistence of a child admission and again before
external projection. A stale default branch snapshot terminalizes the root as
`owner-review-required`; it never silently retargets to a new commit. The
visited-surface set is append-only for the root snapshot.

## Terminal states

The root may transition once to exactly one of:

- `baseline-complete` — all admitted children are terminal and no remaining
  unvisited selected gap is eligible;
- `owner-review-required` — stale snapshot, unresolved review, or a decision
  requiring owner choice;
- `blocked-on-product-decision` — documentation cannot be accurate without a
  product decision;
- `budget-exhausted` — an admission would exceed a configured limit;
- `cancelled` — owner explicitly stops the root.

Terminal projection posts one compact root comment, preserves the final
provenance record, and performs no new child admission.

## Recovery and verification

All controller operations use persist-before-action action records with a
stable action ID. Reconciliation scans non-terminal roots with a bounded
cursor, re-emits incomplete idempotent actions, and never uses webhook
delivery IDs as logical identity. Tests cover duplicate delivery, restart,
stale snapshot, exhausted budget, visited surface, ambiguous decision,
partial GitHub/City projection, and terminal no-expansion behavior.

The acceptance smoke uses a repository fixture: explicit root → one bounded
gap → one linked issue and bead → worker-owned docs PR → root terminal state.
