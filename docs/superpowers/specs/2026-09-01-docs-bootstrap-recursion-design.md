# Bounded Documentation Journey Design

## Outcome

Every documentation request enters one documentation journey for one GitHub
repository. The journey traverses from the repository documentation entry
point toward one declared reader role and job, uses the existing
TechDocs/docs-impact decision as its only documentation-analysis unit,
projects selected bounded gaps into linked GitHub issues and City beads, and
stops with a durable, human-readable terminal state.

This is additive to PR review. A pull request, issue, or explicit operator
request is a source adapter: each supplies provenance and the same normalized
journey contract. Source adapters do not decide documentation content.

## Authority and boundaries

The GitHub pack owns authenticated GitHub projection through its existing App
commands. The controller may create an App-owned issue, comment, branch, or
documentation PR only after the root admission and an exact, persisted
docs-impact result authorize that operation. It never writes to an author's
branch and never merges.

The TechDocs skill decides whether a concrete evidence surface needs docs. IDD
provides planning, issue lifecycle, critique, CI, acceptance, and closure
discipline. The journey controller only carries provenance, evaluates
mechanical admission rules, persists actions before side effects, and
reconciles them.

## Reader journey contract

Each request begins traversal at the repository documentation entry point: a declared
documentation index when present, otherwise `README.md`. Each request fixes
`domain` to `techdocs` and declares:

- `role` — one small, repository-defined role such as `developer`,
  `operator`, or `end-user`;
- `job` — the concrete outcome the reader is trying to achieve;
- `starting_context` — prior knowledge, environment, or entry surface needed
  to interpret the job;
- `success_condition` — observable evidence that the reader can complete the
  job; and
- `backfill_policy` — `blocking-only` or `record-debt`.

The controller does not infer a persona, product promise, or user journey
from code alone. A request is rejected when these values are absent. The role
is not a marketing persona: it constrains the reader's job and expected
context.
Future domains may define their own role libraries, but this controller does
not accept sales or marketing requests.

The reviewer evaluates a path from the documentation entry point and request context
toward the declared job.
A gap that blocks that path may be admitted as remediation. A related gap
that does not block the path is documentation debt: under `record-debt`, the
controller may create one provenance-linked, non-executing GitHub issue; it
must not create a Bead, dispatch a worker, create a branch, or recurse from
that issue. Under `blocking-only`, it records no debt issue.

## Durable model

A **journey run** is the durable record for a normalized request at a pinned
repository snapshot. The documentation entry point is navigation metadata,
not an execution root or a special bootstrap mode. Every source adapter binds
to the same journey-run model, with a source envelope containing kind, stable
ID, URL, and projection capabilities. Each journey run has an immutable
logical identity:

`github-docs-journey:<repository_id>:<source_key>:<default_branch_sha>`

The persisted record includes repository and installation identity, source
envelope, reader journey contract, documentation entry point, default branch
ref/SHA, configured budgets, current counters, visited evidence-surface keys,
terminal state, and child records. A child key is the SHA-256 digest of the
journey identity plus the canonical docs-impact decision identity and
normalized evidence-surface paths. Replays therefore adopt existing records
rather than create duplicate issues, beads, or PRs.

Every child carries its source provenance, optional generated parent-issue
URL, `depth`, `journey_identity`, `snapshot_sha`, and the decision digest. A
child may be admitted only if all required values match the persisted journey
snapshot. Existing v1 bootstrap records and logical IDs remain readable until
they are terminal; migration must not duplicate their external resources.

## Admission and expansion

The entrypoint is any request carrying a complete journey contract. The
controller snapshots the default branch and documentation entry point before
any analysis. It creates a journey run and initial source status only when
the traversal needs durable external work. A source may continue only the
journey it is bound to; a source without that binding may start its own
declared journey, but it may not expand another journey or create unrelated
work from an unqualified docs-impact decision.

A result may create one active child only when it is a validated, exact
`docs-change-required` decision for that snapshot, it blocks the declared
reader journey, the evidence surface was not previously visited, all budgets
remain available, and the decision has no product ambiguity. The controller
creates the GitHub child issue and City bead idempotently, then assigns the
docs-journey worker. The worker follows vendored TechDocs and IDD, creates
an App-owned documentation branch/PR, and reports its result to the child
issue.

`no-impact` and `docs-sufficient` consume no child budget. Non-blocking
documentation debt consumes a debt-issue budget only and never an active-child
or PR budget. `inconclusive`, unsupported evidence, an incompatible snapshot,
or product ambiguity do not retry autonomously; they set the appropriate root
terminal/escalation state.

## Guardrails

Defaults are deliberately small and must be explicit in the journey record:

- maximum depth: `2`;
- maximum admitted children: `8`;
- maximum documentation PRs: `4`;
- maximum documentation-debt issues: `8`;
- maximum elapsed run time: `24h`;
- maximum consecutive non-progress reconciliations: `3`.

Budget checks occur before persistence of a child or debt admission and again
before external projection. A stale default branch snapshot terminalizes the
root as `owner-review-required`; it never silently retargets to a new commit.
The visited-surface set is append-only for the journey snapshot.

## Terminal states

The journey run may transition once to exactly one of:

- `baseline-complete` — all admitted children are terminal and no remaining
  unvisited selected gap is eligible;
- `owner-review-required` — stale snapshot, unresolved review, or a decision
  requiring owner choice;
- `blocked-on-product-decision` — documentation cannot be accurate without a
  product decision;
- `budget-exhausted` — an admission would exceed a configured limit;
- `cancelled` — owner explicitly stops the root.

provenance record, and performs no new child admission.
Terminal projection posts one compact source status where that capability is
available, preserves the final provenance record, and performs no new child
admission.
provenance record, and performs no new child admission.

## Recovery and verification

All controller operations use persist-before-action action records with a
stable action ID. Reconciliation scans non-terminal journey runs with a bounded
cursor, re-emits incomplete idempotent actions, and never uses webhook
delivery IDs as logical identity. Tests cover duplicate delivery, restart,
stale snapshot, exhausted budget, visited surface, ambiguous decision,
partial GitHub/City projection, and terminal no-expansion behavior.

The acceptance smoke uses a repository fixture: normalized request →
documentation entry point → one bounded blocking gap → one linked issue and
bead → worker-owned docs PR → terminal journey state. A non-blocking gap may
produce only an inactive debt bud; it cannot dispatch, branch, recurse, or
gain descendants.
