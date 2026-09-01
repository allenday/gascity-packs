# Portable Issue Delivery Protocol

## Authority

The driver is the sole external writer and uses one automation identity. Subagents return structured evidence. `role` records functional responsibility; it does not imply a separate tracker identity.

Serialize writes per issue. Before every mutation, read the issue and its latest valid event. After mutation, read it again and confirm the intended result.

## Graph Projection

Let plan nodes be independently checkable work units and directed edges mean “must resolve before this issue may resolve.”

- One connected acyclic path, with every node having at most one predecessor and one successor: keep one issue and an ordered inline plan.
- Any fan-out, fan-in, disconnected set, or other non-path topology: create an issue DAG and link every edge in portable Markdown.

Native parent, sub-issue, or dependency features may mirror the graph. Markdown issue links remain the portable record.

## States and Transitions

| State | Entry evidence |
|---|---|
| `planned` | objective, known constraints, plan or child graph, acceptance basis |
| `implementation` | assigned implementation role and linked working change when available |
| `critique` | reviewable current revision and independent critic |
| `ci` | approved critique for the same complete revision |
| `acceptance` | required CI green for that revision and dependency integration current |
| `ready_to_close` | issue-level acceptance evidence, closed dependencies, delivered change set |
| `closed` | fresh driver reconciliation and explicit close action |

Implementation may start before dependencies close. `ready_to_close` may not.

Any code/configuration/content change to the delivered revision, or any CI failure, transitions back to `implementation` and invalidates critique, CI, acceptance, and readiness. Review the full new revision. There are no emergency, authority, small-diff, or CI-only exceptions.

Non-implementation issues explicitly record `change_set: none` and use an appropriate independent critique artifact.

## Parent Rule

A parent's dependency sub-graph must be terminal before the parent enters its final critique. Then independently assess the assembled outcome, run integration CI/QA, validate parent acceptance, and close through the same state machine. Child closure is evidence, never a parent close trigger.

## Event Envelope

Append a visible summary followed by one machine-readable HTML comment:

```markdown
### IDD: critique → ci

Independent critique passed for revision `abc123`; required CI is now pending.

<!-- issue-driven-development:event
{"version":1,"operation_id":"idd-<uuid>","previous_event_id":"idd-<uuid>","timestamp":"<RFC3339>","issue":"<provider-url>","role":"driver","phase":"ci","from":"critique","to":"ci","plan_version":3,"change_set":"<pr-url-or-none>","revision":"<immutable-id-or-none>","dependencies":["<issue-url>"],"evidence":["<review-url>"],"summary":"<concise result>"}
-->
```

Required properties:

- `operation_id` is globally unique and stable across retries.
- `previous_event_id` links the issue-local event chain.
- Evidence uses durable URLs and immutable revision/run IDs where possible.
- `plan_version` increments on amendments.
- The visible summary and JSON must agree.

Before retrying a failed write, search for `operation_id`. If an equivalent event exists, treat the write as successful. If it conflicts, stop and reconcile; never append a second interpretation under the same ID.

## Acceptance Evidence

Acceptance need not be exhaustively known at creation. Record the initial objective, constraints, and known checks. Amend these as discovery proceeds, with rationale. Before readiness, record what was actually validated, the observed result, and links/logs/screenshots or other durable evidence.

CI proves automated repository checks. Acceptance proves the issue's intended outcome. Neither substitutes for the other.

## Integration Completeness

Before a PR for a fan-in, webhook, or external-system controller, obtain an independent interface-completeness review. It must cover provider version contracts, authority boundaries, stable logical event identity versus delivery receipts, bounded reconciliation and cursor recovery, and immutable provenance for any plan or approval. A discovered missing contract amends the issue or creates a linked issue before readiness; passing unit tests do not waive it.

## Closure Checklist

Re-read and verify:

- latest plan version is in force;
- all dependencies are closed;
- implementation-bearing work is delivered and linked;
- independent critique covers the complete delivered revision;
- required CI is green on the final relevant revision/integration state;
- issue-level acceptance evidence is present;
- parent-level gates ran independently when this is a parent;
- no later event invalidates a gate.

After every merge, place the issue in a closure sweep. Record either the missing CI/acceptance/readiness evidence or the explicit closure sequence immediately; do not rely on a later session to remember it.

Append `ready_to_close`, re-read, explicitly close, confirm native state is closed, then append or otherwise preserve the terminal closure event according to provider capabilities. If the provider cannot comment after closure, append the closure event immediately before closing and confirm state afterward.

## Amendments and Recovery

- Append amendments; do not silently edit away prior decisions.
- Re-project topology when edges change.
- Invalidate downstream readiness when dependencies or integration change.
- On stale or contradictory state, stop mutation, record a reconciliation event, and resume only from the last proven valid phase.
- On missing required capability, leave the issue open and report the exact missing operation.
