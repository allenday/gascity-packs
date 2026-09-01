# Bounded Documentation Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, bounded GitHub documentation-bootstrap workflow that composes vendored IDD, TechDocs, and the existing docs-impact decision contract.

**Architecture:** A small durable bootstrap controller owns root/child provenance, admission budgets, idempotent action records, and terminal projection. The existing TechDocs/docs-impact artifact remains the sole documentation judgment. A formula invokes the controller for an explicit root and dispatches a docs-bootstrap worker only after a child is mechanically admitted.

**Tech Stack:** Python 3 standard library, TOML pack formulas, GitHub App commands, City Beads, unittest.

**Spec:** `docs/superpowers/specs/2026-09-01-docs-bootstrap-recursion-design.md`

## Global Constraints

- Vendor `managing-issue-driven-development` completely under `github/skills/` with immutable source provenance.
- Root identity is `github-docs-bootstrap:<repository_id>:<root_issue_number>:<default_branch_sha>`.
- Only explicit roots expand; PR docs-impact checks never create bootstrap children.
- Child keys bind root identity, exact docs-impact identity, and normalized evidence paths.
- Defaults: depth `2`, children `8`, documentation PRs `4`, elapsed time `24h`, non-progress reconciliations `3`.
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

### Task 2: Define and test the bootstrap durable model

**Files:**
- Create: `github/scripts/github_docs_bootstrap.py`
- Create: `github/tests/test_github_docs_bootstrap.py`

**Interfaces:**
- `new_root(request, now) -> dict` constructs the immutable root record.
- `admit_child(root, decision, now) -> (root, action | None)` admits only an exact eligible docs-impact result.
- `reconcile_root(root, now) -> (root, list[action])` emits persisted incomplete actions and terminalizes deterministically.

- [ ] Write failing tests for exact root identity, duplicate decision adoption, visited-surface suppression, stale snapshot, each budget boundary, ambiguity, and every terminal state.
- [ ] Run `python3 -m unittest github.tests.test_github_docs_bootstrap -v`; verify failures name missing module/functions.
- [ ] Implement serialization-safe root/child records, normalized path digesting, mechanical admission, and terminal transitions. Do not parse or reinterpret TechDocs rationale.
- [ ] Re-run the focused suite and full GitHub suite.
- [ ] Commit `feat(github): add bounded docs bootstrap model`.

### Task 3: Add idempotent GitHub/City projection actions

**Files:**
- Modify: `github/scripts/github_docs_bootstrap.py`
- Modify: `github/scripts/github_intake_common.py`
- Modify: `github/tests/test_github_docs_bootstrap.py`
- Modify: `github/tests/test_github_intake_common.py`

**Interfaces:**
- `project_actions(root, adapter) -> root` consumes durable `create_issue`, `create_bead`, `assign_bead`, `post_root_status`, and `create_docs_pr` action IDs.
- Adapter methods must adopt previously-created external resources by stable logical ID.

- [ ] Write failing tests that simulate crash-after-persist-before-project, duplicate delivery, partial issue/bead creation, and replay after restart.
- [ ] Run the focused tests; verify projected resources are not duplicated.
- [ ] Implement persist-before-action updates and existing GitHub App/Bead command adapters; use only App-owned issues, branches, and PRs.
- [ ] Run focused and full suites.
- [ ] Commit `feat(github): project bootstrap remediation idempotently`.

### Task 4: Expose the explicit-root formula and worker contract

**Files:**
- Create: `github/formulas/github-docs-bootstrap.formula.toml`
- Create: `github/agents/docs-bootstrap/agent.toml`
- Create: `github/agents/docs-bootstrap/prompt.template.md`
- Modify: `github/pack.toml`
- Modify: `github/README.md`
- Create: `github/tests/test_github_docs_bootstrap_formula.py`

**Interfaces:**
- Formula variables include repository, installation ID, root issue URL/number, default branch SHA, and explicit budgets.
- Worker input is one admitted child record; output is an IDD-compliant child update and at most one App-owned documentation PR.

- [ ] Write failing tests that reject formula defaults that allow PR-triggered expansion, missing qualified provenance, or a worker instruction that permits author-branch writes/merge.
- [ ] Run the focused formula tests and verify the expected failures.
- [ ] Implement the formula steps: load explicit root, snapshot/admit, project, run child, reconcile, and terminal status. Vendor-skill instructions must direct IDD lifecycle work, while TechDocs decides documentation content.
- [ ] Document the opt-in command, prerequisites, budgets, terminal states, and explicit non-goal for ordinary PR checks.
- [ ] Run focused tests, full suite, and re-read changed documentation against code.
- [ ] Commit `feat(github): add explicit docs bootstrap formula`.

### Task 5: Validate the end-to-end bounded graph

**Files:**
- Create: `github/tests/test_github_docs_bootstrap_smoke.py`
- Modify: `github/scripts/github_docs_bootstrap.py`
- Modify: `github/README.md`

**Interfaces:**
- Fixture flow: explicit root → exact `docs-change-required` decision → one issue/bead/worker PR projection → terminal root status.

- [ ] Write the failing smoke test using a fake GitHub/City adapter with a root-owned branch and an accepted docs-impact decision.
- [ ] Run it and verify the flow fails before the complete controller path exists.
- [ ] Implement only missing glue needed for a finite graph; assert ordinary PR decision intake cannot invoke bootstrap admission.
- [ ] Run smoke, full GitHub suite, and `git diff --check`.
- [ ] Commit `test(github): smoke bounded docs bootstrap graph`.

### Task 6: Delivery review and IDD reconciliation

**Files:**
- Modify: `github/README.md`
- Modify: `docs/superpowers/specs/2026-09-01-docs-bootstrap-recursion-design.md` only if verification changes an externally visible contract.

- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py'` and capture the final test count.
- [ ] Independently review the complete branch against the spec, including authority, idempotency, stale snapshot, and no-expansion boundaries.
- [ ] Open a PR referencing `#26`, `#27`, and `#28` without auto-close keywords.
- [ ] Append current-revision critique, CI, and acceptance evidence to the three leaf issues; do not close them until dependency and parent gates are current.
- [ ] Commit any documentation-only corrections from review separately.
