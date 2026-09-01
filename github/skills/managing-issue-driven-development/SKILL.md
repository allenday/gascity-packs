---
name: managing-issue-driven-development
description: Use when software work must be planned, implemented, reviewed, validated, or closed through an issue tracker and CI system, especially with multiple agents, dependency graphs, pull requests, stale open issues, or GitHub/Gitea delivery workflows.
---

# Managing Issue-Driven Development

## Overview

Treat each issue as a uniform delivery state machine. The driver alone mutates external systems; implementation, critique, and QA agents return evidence for the driver to record.

**Core principle:** work may pipeline eagerly, but resolution advances only on current, issue-local evidence.

Read [references/protocol.md](references/protocol.md) before mutating tracker state. Read only the references for the selected tracker and CI provider.

## Compose, Do Not Replace

This skill owns issue projection, external status, and closure. Use the applicable Superpowers skills for the work itself:

- **REQUIRED FOR PLANNING:** `superpowers:brainstorming` and `superpowers:writing-plans`
- **REQUIRED FOR IN-SESSION EXECUTION:** `superpowers:subagent-driven-development`
- **REQUIRED FOR REVIEW:** `superpowers:requesting-code-review`
- **REQUIRED FOR CI FAILURES:** `superpowers:systematic-debugging`
- **REQUIRED BEFORE READY/CLOSE:** `superpowers:verification-before-completion`
- **REQUIRED FOR INTEGRATION:** `superpowers:finishing-a-development-branch`

## Workflow

1. Discover tracker and CI capabilities. Use [github.md](references/github.md) or [gitea.md](references/gitea.md), plus [github-actions.md](references/github-actions.md) or [woodpecker.md](references/woodpecker.md). Stop if required read/write evidence operations are unavailable.
2. Compile the approved plan into a dependency graph. Keep one issue with an ordered inline plan only when the graph is a single linked list. Any fan-out, fan-in, disconnected component, or other non-linear DAG requires linked issues.
3. Record the plan, dependency edges, acceptance basis, and initial `planned` event. Provider-native fields are optional mirrors.
4. Dispatch work eagerly when useful. Agents never post tracker status directly; they return evidence to the driver.
5. Advance each issue through `planned → implementation → critique → ci → acceptance → ready_to_close → closed` using protocol events.
6. On every merge, queue a leaf-closure sweep: reconcile PR head/merge/CI, then record CI, acceptance, readiness, and explicit closure or the exact remaining gate. A merge is never closure.
7. Before closing, re-read external state and verify every gate against the current revision. Close explicitly; never rely on merge keywords, child completion, or tracker automation.

## Non-Negotiable Gates

- Every implementation-bearing issue links a PR or equivalent reviewable change set.
- The critic did not implement or edit that issue. A critic may review many other issues.
- Critique covers the complete current revision, not merely a delta.
- Any implementation change or CI failure returns to `implementation`, invalidating later gates. Repeat full independent critique and CI.
- CI and issue-level acceptance validation are separate evidence gates.
- A fan-in or external-integration issue requires a dependency-interface completeness review before PR creation. Record missing authority, provenance, reconciliation, provider-contract, or recovery semantics as an amendment or a new issue; do not ship a webhook-only happy path as complete integration.
- Tracker ingress/reconciliation work defines stable logical event identity separately from delivery receipts, bounded scan/cursor semantics, crash-safe cursor advancement, and recovery tests.
- If approval depends on a plan, acceptance requires authenticated immutable plan provenance, amendment semantics, and approval ordering; mutable text alone is not evidence.
- Dependencies need not be closed to start implementation, but all must be closed before `ready_to_close`. Refresh integration evidence after dependencies resolve.
- A parent is a delivery issue, not a roll-up. After its entire sub-graph closes, run the parent's own critique, integrated CI/QA, acceptance validation, and explicit close.
- Deadlines, authority, tiny changes, prior approval, and green CI create no waiver path.

## Amendments

Append the changed plan or acceptance basis and its rationale. Never rewrite history silently. If topology changes, re-project the graph. Invalidate downstream readiness until dependency and integration evidence is current.

## Red Flags — Stop

- An agent other than the driver is about to mutate tracker state.
- “The previous review still covers most of it.”
- “Green CI is enough this time.”
- “The parent can close because every child closed.”
- A provider label, project column, or native dependency field is the only workflow record.
- A close action is about to run without a fresh state read.
- A mock accepts an endpoint, webhook action, or payload shape not verified against the pinned provider version.

All indicate the lifecycle is incomplete. Return to the required phase; do not invent an exception.
