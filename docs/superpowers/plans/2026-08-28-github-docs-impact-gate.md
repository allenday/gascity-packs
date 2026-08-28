# GitHub Docs-Impact Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a revision-bound GitHub docs-impact Check Run that can become a required dogfood merge gate.

**Architecture:** Extend the signed GitHub intake path with a GitHub-specific PR-source-bead convention and a docs-impact command. It records/reconciles source work by immutable repository ID, PR number, and head SHA, then projects the result through GitHub Checks. Compose later deploys the worker behind a loopback-only Tailscale Funnel route.

**Tech Stack:** Python 3 standard library, existing `gc bd` command seam, GitHub App REST API, Docker Compose, Tailscale Funnel, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-28-github-docs-impact-gate-design.md`

## Global Constraints

- Do not modify Gas City core.
- Source identity is `github-pr:<repository-id>:<number>:<head-sha>`, never a delivery ID.
- Preserve the existing GitHub-pack behavior and its 111-test baseline.
- Keep the worker loopback-only; expose only `/v0/github/webhook`.
- A `needs-human-decision` conclusion is not merge-success.

---

### Task 1: Normalize PR revision identity

**Files:**
- Modify: `github/scripts/github_intake_service.py`
- Modify: `github/scripts/github_intake_common.py`
- Test: `github/tests/test_github_intake_service.py`
- Test: `github/tests/test_github_intake_common.py`

**Interfaces:**
- `github_pr_context(payload) -> dict[str, str]` requires repository ID, repository name, PR number, full head SHA, base ref, head ref, and URL.
- `github_pr_source_key(context) -> str` returns `github-pr:<repository-id>:<number>:<head-sha>`.
- `github_event_env` exports `GC_GITHUB_PR_HEAD_SHA`.

- [ ] Write failing tests for valid context, missing identity fields, duplicate source keys, and changed-head source keys.
- [ ] Run `python3 -m unittest github.tests.test_github_intake_service github.tests.test_github_intake_common -v`; expect missing helpers.
- [ ] Implement strict context/key helpers and head-SHA event export.
- [ ] Re-run focused tests; commit `feat(github): normalize pull request source identity`.

### Task 2: Add docs-impact source work and Check Run projection

**Files:**
- Create: `github/scripts/github_intake_docs_impact.py`
- Modify: `github/scripts/github_intake_common.py`
- Modify: `github/scripts/github_intake_service.py`
- Test: `github/tests/test_github_intake_docs_impact.py`
- Test: `github/tests/test_github_intake_common.py`

**Interfaces:**
- `github_intake_docs_impact.py evaluate` consumes signed event context and creates/reuses source work with `external.source_key`, `github.repository_id`, `github.pr_number`, and `github.head_sha`.
- `create_or_update_check_run(app_cfg, installation_id, owner, repo, head_sha, name, status, conclusion, output) -> dict[str, Any]`.
- Result kinds are exactly `no-impact`, `docs-update-proposed`, and `needs-human-decision`.

- [ ] Write failing tests asserting source metadata and a Checks API payload with the exact `head_sha`.
- [ ] Run the focused tests; expect missing evaluator/check helper.
- [ ] Implement source-bead creation through the existing `gc bd` subprocess seam, Check Run creation/update using an installation token, and manifest `checks: write` permission.
- [ ] Bootstrap deterministic policy: docs/test/CI-only paths are `no-impact`; code plus docs paths is `docs-update-proposed`; remaining code is `needs-human-decision`. Include changed paths and source bead ID in check output.
- [ ] Re-run focused tests; commit `feat(github): project docs impact to revision-bound checks`.

### Task 3: Wire event rules and recovery tests

**Files:**
- Modify: `github/README.md`
- Modify: `github/scripts/github_intake_service.py`
- Test: `github/tests/test_github_intake_service.py`
- Test: `github/tests/test_github_intake_docs_impact.py`

**Interfaces:**
- A `pull_request` rule for `opened`, `reopened`, `synchronize`, and `ready_for_review` executes the evaluator through the existing command-action environment.
- The normal durable delivery receipt remains unchanged.

- [ ] Write failing rule tests for allowed actions, duplicate delivery serialization, and distinct source work for a new head SHA.
- [ ] Implement/document the command rule using an installation-token environment.
- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py' -v`; commit `docs(github): configure docs impact PR intake`.

### Task 4: Compose deployment and controlled dogfood

**Files:**
- Modify: `../gascity-compose/compose.yaml`
- Modify: `../gascity-compose/.env.example`
- Modify: `../gascity-compose/nginx/nginx.conf`
- Create: `../gascity-compose/config/github-intake/rules.toml`
- Create: `../gascity-compose/scripts/github-docs-impact-smoke.sh`
- Test: `../gascity-compose/scripts/tests/test_github_docs_impact.sh`

- [ ] Write render and signed-payload smoke tests: no host port for the worker; duplicate payload reuses source identity; a changed head creates distinct source identity.
- [ ] Add a profile-gated loopback-only worker with durable intake state, webhook secret, and GitHub App identity resolver.
- [ ] Immediately before exposure, pause Infralink, configure Funnel with `--https=443 --set-path=/v0/github/webhook`, configure the GitHub `pull_request` webhook, and re-check the public endpoint without printing secrets.
- [ ] Dogfood an advisory PR, recording immutable head SHA and check URL on issue #50; push a new head and verify the old result is stale.
- [ ] Require only `Gas City / docs-impact` after advisory success; verify pending/non-success blocks merge and current-head success restores eligibility.
- [ ] Run pack tests and compose smoke tests; commit pack and compose changes separately, then open linked PRs without auto-close keywords.
