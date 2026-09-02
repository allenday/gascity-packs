# Bounded Documentation Journey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded GitHub documentation-journey workflow that traverses from the repository documentation entry point and composes vendored IDD, TechDocs, and the existing docs-impact decision contract.

**Architecture:** A small durable journey controller owns a fixed reader-journey contract, generic source/child provenance, admission budgets, idempotent action records, debt-only projection, and terminal projection. The documentation entry point is navigation, not a separate bootstrap root. The existing TechDocs/docs-impact artifact remains the sole documentation judgment. Source adapters normalize PR, issue, or explicit requests into one journey-run contract; the formula dispatches a docs-journey worker only after a blocking child is mechanically admitted.

**Tech Stack:** Python 3 standard library, TOML pack formulas, GitHub App commands, City Beads, unittest.

**Spec:** `docs/superpowers/specs/2026-09-01-docs-bootstrap-recursion-design.md`

## Global Constraints

- Vendor `managing-issue-driven-development` completely under `github/skills/` with immutable source provenance.
- Journey identity is `github-docs-journey:<repository_id>:<source_key>:<default_branch_sha>`; v1 bootstrap identities and action IDs remain readable until terminal migration is complete.
- Traversal begins at a declared documentation index or `README.md`; requests are `domain: techdocs` only and require `role`, `job`, `starting_context`, `success_condition`, and `backfill_policy` (`blocking-only` or `record-debt`).
- Every qualified source may start its own declared journey from the documentation entry point. A source may continue only the journey to which it is bound; no source may expand another journey or use an unqualified docs-impact result to create unrelated work.
- Child keys bind journey identity, exact docs-impact identity, and normalized evidence paths.
- Defaults: depth `2`, active children `8`, documentation PRs `4`, debt issues `8`, elapsed time `24h`, non-progress reconciliations `3`.
- Terminal states are exactly `baseline-complete`, `owner-review-required`, `blocked-on-product-decision`, `budget-exhausted`, and `cancelled`.
- Persist an idempotent action before GitHub/City side effects; never modify an author branch or merge.

---

### Task 1: Vendor IDD skill with provenance

**Files:**
- Create: `github/skills/managing-issue-driven-development/SKILL.md`
- Create: `github/skills/managing-issue-driven-development/references/protocol.md`
- Create: `github/skills/managing-issue-driven-development/references/github.md`
- Create: `github/skills/managing-issue-driven-development/references/github-actions.md`
- Modify: `github/vendor/personal-agent-skills/upstream.toml`
- Create: `github/tests/test_vendored_skills.py`

**Interfaces:**
- Produces a complete local skill tree and TOML provenance entry used by the docs-bootstrap worker.

- [ ] Write a failing test that requires the four IDD files and a TOML entry with repository, 40-character revision, source path, and license.
- [ ] Run `python3 -m unittest github.tests.test_vendored_skills -v`; verify it fails because the IDD vendor tree is absent.
- [ ] Copy the exact source skill and required references; add immutable provenance without changing the existing TechDocs entry.
- [ ] Run the focused test and `python3 -m unittest discover -s github/tests -p 'test_*.py'`.
- [ ] Commit `feat(github): vendor issue-driven-development skill`.

### Task 1b: Replace the bootstrap control plane without duplicating work

**Files:**
- Rename: `github/scripts/github_docs_bootstrap.py` → `github/scripts/github_docs_journey.py`
- Rename: `github/scripts/github_intake_docs_bootstrap_commands.py` → `github/scripts/github_intake_docs_journey_commands.py`
- Rename: `github/formulas/github-docs-bootstrap.formula.toml` → `github/formulas/github-docs-journey.formula.toml`
- Rename: `github/agents/docs-bootstrap/` → `github/agents/docs-journey/`
- Rename matching tests and update `github/pack.toml`, `github/README.md`

**Interfaces:**
- New records use a normalized source envelope and `github-docs-journey` identity.
- Legacy `github-docs-bootstrap` records, file-store paths, and logical action IDs are read and projected idempotently until terminal.

- [ ] Write failing compatibility tests proving a v1 persisted record resumes without a duplicate issue, bead, assignment, PR, or status comment.
- [ ] Write failing source tests proving issue, PR, and explicit requests normalize to the same journey contract; only a source already bound to a journey may continue it.
- [ ] Implement dual-read compatibility and source projection capabilities before removing public bootstrap names. Do not make a mass rename that strands live records.
- [ ] Rename public formula, worker, commands, records, messages, and documentation to `docs-journey`; retain only deliberately tested legacy-read aliases.
- [ ] Run the focused journey and full GitHub suite; inspect persisted action IDs and adoption markers.
- [ ] Commit `refactor(github): unify docs bootstrap as journey lifecycle`.

### Task 2: Define and test the source-agnostic durable model

**Files:**
- Create: `github/scripts/github_docs_journey.py`
- Create: `github/tests/test_github_docs_journey.py`

**Interfaces:**
- `new_journey(request, now) -> dict` constructs the immutable journey record from a normalized source envelope.
- `admit_child(journey, decision, now) -> (journey, action | None)` admits only an exact eligible docs-impact result.
- `reconcile_journey(journey, now) -> (journey, list[action])` emits persisted incomplete actions and terminalizes deterministically.

- [ ] Write failing tests for the required `techdocs` reader-journey contract; documentation-entry selection (`docs` index then `README.md`); normalized issue/PR/explicit source binding; exact journey identity; legacy-record read compatibility; duplicate decision adoption; blocking versus non-blocking gap disposition; `blocking-only` versus `record-debt`; visited-surface suppression; stale snapshot; each active/debt budget boundary; ambiguity; and every terminal state.
- [ ] Run `python3 -m unittest github.tests.test_github_docs_journey -v`; verify failures name missing module/functions.
- [ ] Implement serialization-safe traversal/journey/child/debt records, documentation-entry selection, normalized source envelopes, compatibility reads, normalized path digesting, mechanical admission, and terminal transitions. Reject missing/unsupported journey contracts. A non-blocking gap may emit only a debt-issue intent under `record-debt`; it must never emit a Bead, worker, branch, PR, or expansion intent. Do not parse or reinterpret TechDocs rationale.
- [ ] Re-run the focused suite and full GitHub suite.
- [ ] Commit `feat(github): add bounded docs journey model`.

### Task 3: Add idempotent GitHub/City journey projection actions

**Files:**
- Modify: `github/scripts/github_docs_journey.py`
- Modify: `github/scripts/github_intake_common.py`
- Modify: `github/tests/test_github_docs_journey.py`
- Modify: `github/tests/test_github_intake_common.py`

**Interfaces:**
- `project_actions(journey, adapter) -> journey` consumes durable `create_issue`, `create_debt_issue`, `create_bead`, `assign_bead`, `post_journey_status`, and `create_docs_pr` action IDs.
- Adapter methods must adopt previously-created external resources by stable logical ID.

- [ ] Write failing tests that simulate crash-after-persist-before-project, duplicate delivery, partial issue/bead creation, debt-issue replay, and restart. Prove that `create_debt_issue` cannot invoke any active-work adapter.
- [ ] Run the focused tests; verify projected resources are not duplicated.
- [ ] Implement persist-before-action updates and existing GitHub App/Bead command adapters; use only App-owned issues, branches, and PRs.
- [ ] Run focused and full suites.
- [ ] Commit `feat(github): project docs journey remediation idempotently`.

### Task 4: Expose the source-agnostic formula and worker contract

**Files:**
- Create: `github/formulas/github-docs-journey.formula.toml`
- Create: `github/agents/docs-journey/agent.toml`
- Create: `github/agents/docs-journey/prompt.template.md`
- Modify: `github/pack.toml`
- Modify: `github/README.md`
- Create: `github/tests/test_github_docs_journey_formula.py`

**Interfaces:**
- Formula variables include repository, installation ID, documentation-entry path, normalized source provenance, default branch SHA, the required `techdocs` reader-journey contract, and explicit budgets.
- Worker input is one admitted child record; output is an IDD-compliant child update and at most one App-owned documentation PR.

- [ ] Write failing tests that reject missing documentation-entry/source provenance, missing journey contracts, cross-journey continuation, missing qualified provenance, or a worker instruction that permits author-branch writes/merge.
- [ ] Run the focused formula tests and verify the expected failures.
- [ ] Implement the formula steps: load or create normalized journey, snapshot/admit, project, run child, reconcile, and terminal status. Vendor-skill instructions must direct IDD lifecycle work, while TechDocs decides documentation content.
- [ ] Document source adapters, prerequisites, budgets, terminal states, legacy migration, and the boundary that unqualified docs-impact results cannot create work.
- [ ] Run focused tests, full suite, and re-read changed documentation against code.
- [ ] Commit `feat(github): add docs journey formula`.

### Task 5: Validate the end-to-end bounded journey graph

**Files:**
- Create: `github/tests/test_github_docs_journey_smoke.py`
- Modify: `github/scripts/github_docs_journey.py`
- Modify: `github/README.md`

**Interfaces:**
- Fixture flow: normalized request → documentation entry point (`README.md` fallback) → exact blocking `docs-change-required` decision → durable journey run → one issue/bead/worker PR projection → terminal journey status; any qualified source may start its own declared journey, while a source may continue only its bound journey; a non-blocking gap yields at most one inactive debt bud and no active work.

- [ ] Write the failing smoke test using a fake GitHub/City adapter with a root-owned branch and an accepted docs-impact decision.
- [ ] Run it and verify the flow fails before the complete controller path exists.
- [ ] Implement only missing glue needed for a finite graph; assert generic source admission never expands an unrelated journey and debt buds never execute.
- [ ] Run smoke, full GitHub suite, and `git diff --check`.
- [ ] Commit `test(github): smoke bounded docs journey graph`.

### Task 6: Delivery review and IDD reconciliation

**Files:**
- Modify: `github/README.md`
- Modify: `docs/superpowers/specs/2026-09-01-docs-bootstrap-recursion-design.md` only if verification changes an externally visible contract.

- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py'` and capture the final test count.
- [ ] Independently review the complete branch against the spec, including authority, idempotency, stale snapshot, and no-expansion boundaries.
- [ ] Open a PR referencing `#26`, `#27`, and `#28` without auto-close keywords.
- [ ] Append current-revision critique, CI, and acceptance evidence to the three leaf issues; do not close them until dependency and parent gates are current.
- [ ] Commit any documentation-only corrections from review separately.
