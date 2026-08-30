# Durable GitHub Docs-Impact Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every opted-in PR immediately receives one recoverable, GitHub-visible docs-impact check.

**Architecture:** Persist a run before queueing City work and create its Check Run immediately. A separate reconciler advances persisted runs from assignment through candidate validation and terminal Check Run publication, safely retrying after service or City restarts.

**Tech Stack:** Python standard library, GitHub Checks API, Gas City Beads, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-30-github-docs-impact-durable-lifecycle-design.md`

## Global Constraints

- Preserve strict candidate validation and exact-SHA binding.
- Create no duplicate Check Runs or stacked follow-up PRs on retry.
- Do not publish a terminal result for a changed PR head.
- GitHub Check output stays concise; details belong on the City page.

---

### Task 1: Durable initial Check Run

**Files:**
- Modify: `github/scripts/github_intake_service.py`
- Modify: `github/scripts/github_intake_docs_impact.py`
- Test: `github/tests/test_github_intake_docs_impact.py`

**Produces:** `begin_docs_impact_run(token, context)` creates/adopts one in-progress check and persists its ID before City queueing.

- [ ] Write a test asserting `evaluate()` creates one `in_progress` check with `Gas City is reviewing documentation impact` before it queues the assignment.
- [ ] Run the focused test; expect failure because `evaluate()` currently creates no check.
- [ ] Add a persisted `accepted` state, external ID, deadline, and empty candidate projection to the run record.
- [ ] Implement `begin_docs_impact_run()` to create or adopt the Check Run by external ID and return its ID without terminal publication.
- [ ] Call it after current-head validation and before `queue_agent_review()`.
- [ ] Run `python3 -m unittest github.tests.test_github_intake_docs_impact`.
- [ ] Commit: `feat(github): publish docs impact checks immediately`.

### Task 2: Reconciler-owned completion

**Files:**
- Create: `github/scripts/github_intake_docs_impact_reconciler.py`
- Modify: `github/scripts/github_intake_docs_impact_pipeline.py`
- Modify: `github/scripts/github_intake_service.py`
- Test: `github/tests/test_github_intake_docs_impact_reconciler.py`

**Produces:** `reconcile_run(token, context)` advances one durable run idempotently.

- [ ] Write tests for candidate-present completion, duplicate scan adoption, stale-head neutralization, and deadline-expired action-required completion.
- [ ] Run the new test module; expect import failure.
- [ ] Move terminal publication logic behind `reconcile_run()` so it completes the Check Run ID already persisted by Task 1.
- [ ] Implement candidate lookup by immutable assignment digest and exact envelope validation.
- [ ] Implement deadline handling with output title `Documentation impact: review unavailable` and an action-required explanation plus City run link.
- [ ] Change the webhook pipeline to persist/queue only; invoke reconciliation once as an optimization, never as the sole completion path.
- [ ] Run the reconciler and pipeline test modules.
- [ ] Commit: `feat(github): reconcile durable docs impact runs`.

### Task 3: Restart-safe City requeue

**Files:**
- Modify: `github/scripts/github_intake_service.py`
- Modify: `github/scripts/github_intake_docs_impact_reconciler.py`
- Test: `github/tests/test_github_intake_docs_impact_reconciler.py`

**Produces:** expired City leases requeue the same assignment without a new GitHub Check Run.

- [ ] Write a test with an accepted run, no candidate, and an expired City lease; assert queue reuse and unchanged Check Run ID.
- [ ] Run it; expect failure.
- [ ] Persist assignment path/digest and City dispatch identity in the run record.
- [ ] Add a requeue operation guarded by that digest and by current PR head.
- [ ] Ensure it does not overwrite an existing valid candidate or create a second source bead.
- [ ] Run all GitHub intake tests.
- [ ] Commit: `fix(github): recover interrupted city docs reviews`.

### Task 4: Compose scheduler and observability

**Files:**
- Modify: `compose.yaml`
- Modify: `README.md`
- Create: `scripts/github_docs_impact_reconciler_loop.sh`
- Test: `tests/test_compose_github_docs_impact.py`

**Produces:** profile starts a single reconciler loop and documents visible lifecycle semantics.

- [ ] Write a Compose contract test requiring the reconciler service in the `github-docs-impact` profile.
- [ ] Run it; expect failure.
- [ ] Add a credentialed, restartable reconciler service using the same durable state volume and pack mount as intake.
- [ ] Add bounded polling and structured logs containing run locator, state transition, and Check Run ID; never log tokens or patch text.
- [ ] Document the visible GitHub lifecycle and restart recovery behavior.
- [ ] Run `make test` and the Compose config service listing.
- [ ] Commit: `feat(compose): run durable docs impact reconciler`.

### Task 5: Proposal contract and smoke tests

**Files:**
- Modify: `github/agents/docs-impact-reviewer/prompt.template.md`
- Modify: `github/scripts/github_intake_docs_patch_worker.py`
- Modify: `github/scripts/github_intake_docs_impact.py`
- Test: `github/tests/test_github_intake_docs_patch_worker.py`
- Test: `github/tests/test_github_intake_docs_impact_reconciler.py`

**Produces:** validator-compatible proposal artifacts and an end-to-end restart smoke fixture.

- [ ] Write a failing test for a proposal using `evidence_bundle.proposal_identity`; assert it validates and produces one stacked PR link.
- [ ] Run the focused tests; expect failure if any proposal field is missing or extra.
- [ ] Keep the strict proposal schema; make the prompt specify the exact allowed proposal fields and immutable identity source.
- [ ] Add a fixture that creates an accepted run, simulates a City restart, writes a valid proposal candidate, and asserts completion of the original Check Run plus one follow-up PR.
- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py'`.
- [ ] Commit: `test(github): cover durable docs proposal recovery`.

### Task 6: Live dogfood acceptance

**Files:**
- Modify: `github/README.md`

- [ ] Deploy the merged pack and Compose changes.
- [ ] Open a same-repository smoke PR that removes complete docs evidence and changes the related code default.
- [ ] Verify GitHub displays the in-progress check immediately.
- [ ] Restart City and webhook while the check is in progress.
- [ ] Verify the original check reaches proposal-ready action-required and links to exactly one stacked docs PR.
- [ ] Merge that stacked PR into the smoke branch and verify the original PR reruns to a terminal result.
- [ ] Close the smoke PR and document only the verified operator steps.
