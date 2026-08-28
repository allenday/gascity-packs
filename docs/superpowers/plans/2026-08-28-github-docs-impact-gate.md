# City-Agent Docs-Impact Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a GitHub docs-impact check only after a City TechDocs agent returns a validated review for the exact pull-request revision.

**Architecture:** GitHub Intake authenticates and records immutable PR evidence, but publishes no Check Run. It writes a revision-bound TechDocs assignment. The City agent returns a review artifact; a trusted projector validates it, persists a run record, and creates the sole completed GitHub check.

**Tech Stack:** Python 3 standard library, existing `gc bd` seam, GitHub Checks API, Docker Compose, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-28-github-docs-impact-gate-design.md`

## Global Constraints

- Do not modify Gas City core or add a Gitea adapter.
- Source identity remains `github-pr:<repository-id>:<number>:<head-sha>`; delivery IDs remain receipts only.
- No GitHub check, including an in-progress check, exists before a valid City-agent result.
- Every artifact binds repository ID, repository name, PR number, full head SHA, source key, and the `developer-experience-techdocs` skill identity.
- `no-impact` and `docs-sufficient` are successful; `docs-change-required`, `proposal-ready`, and `inconclusive` are not. Missing or invalid artifacts create no check.
- GitHub output contains only decision, rationale, and next action. City IDs, source keys, raw path inventories, and SHA plumbing are never public projection.
- The worker remains networkless, read-only except for its artifact outbox, and receives neither GitHub credentials nor City state.

---

### Task 1: Validate a City TechDocs review artifact

**Files:**
- Modify: `github/scripts/github_intake_docs_patch.py`
- Modify: `github/tests/test_github_intake_docs_patch.py`

**Interfaces:**

```python
def validate_agent_review(document: dict[str, Any]) -> dict[str, Any]: ...
# kind: github-pr-docs-impact-review
# verdict: no-impact | docs-sufficient | docs-change-required | proposal-ready | inconclusive
```

- [ ] Write failing tests for a revision-bound `docs-sufficient` review and rejection of a missing source key, unknown verdict, empty rationale, malformed evidence, and a proposal on any verdict except `proposal-ready`.

```python
def test_validate_agent_review_rejects_unbound_result(self):
    review = valid_agent_review()
    review["identity"].pop("source_key")
    with self.assertRaises(ValueError):
        docs_patch.validate_agent_review(review)
```

- [ ] Run `python3 -m unittest github.tests.test_github_intake_docs_patch -v`; expect failure because `validate_agent_review` does not exist.
- [ ] Implement strict type/identity/skill/evidence/proposal validation and return a normalized, content-digested copy.
- [ ] Re-run the focused suite; expect PASS.
- [ ] Commit `feat(github): validate city docs impact reviews`.

### Task 2: Queue agent work and stop deterministic publication

**Files:**
- Modify: `github/scripts/github_intake_docs_impact.py`
- Modify: `github/scripts/github_intake_service.py`
- Modify: `github/tests/test_github_intake_docs_impact.py`
- Modify: `github/tests/test_github_intake_service.py`

**Interfaces:**

```python
def queue_agent_review(context, source, paths) -> dict[str, Any]: ...
# kind: github-pr-docs-impact-assignment
# agent_skill: developer-experience-techdocs
```

- [ ] Write failing tests proving `evaluate(...)` returns `queued`, creates a descriptor bound to the source key and TechDocs skill, and makes zero GitHub Checks API requests.

```python
def test_evaluate_queues_city_review_without_creating_a_check(self):
    result = docs_impact.evaluate(payload, "delivery-1", "token", paths=["src/cli.py"])
    self.assertEqual(result["status"], "queued")
    self.assertEqual(self.github_requests, [])
```

- [ ] Run `python3 -m unittest github.tests.test_github_intake_docs_impact github.tests.test_github_intake_service -v`; expect failure because current code creates a pending and terminal check.
- [ ] Write the assignment to the existing sanitized inbox with exact identity, source key, changed paths, and requested skill. Remove `classify_paths`, initial check creation, and all path-derived conclusions. A duplicate delivery reuses the assignment; a new SHA produces a new assignment.
- [ ] Re-run focused tests; expect PASS.
- [ ] Commit `feat(github): queue docs impact for city review`.

### Task 3: Project only a validated agent result

**Files:**
- Modify: `github/scripts/github_intake_docs_impact.py`
- Modify: `github/scripts/github_intake_service.py`
- Modify: `github/tests/test_github_intake_docs_impact.py`
- Modify: `github/tests/test_github_intake_service.py`

**Interfaces:**

```python
def project_agent_review(context, source, review) -> dict[str, Any] | None: ...
def publish_agent_review(token, context, review) -> dict[str, Any]: ...
```

- [ ] Write failing tests proving a valid review creates exactly one completed check, missing/wrong-revision review creates no check, and public output contains no City identifier.

```python
def test_run_page_hides_city_identifier_and_collapses_evidence(self):
    page = service.render_docs_impact_run(record_from(valid_agent_review()))
    self.assertNotIn("mc-", page)
    self.assertIn("<details><summary>Evidence", page)
```

- [ ] Run `python3 -m unittest github.tests.test_github_intake_docs_impact github.tests.test_github_intake_service -v`; expect failure because current output derives decisions from paths.
- [ ] Validate and exact-match the artifact, persist it, then create one completed check. Successful verdicts are `no-impact` and `docs-sufficient`; all others are `action_required`. Public summary is exactly rationale plus next action. The run page shows Decision, Why, Next action, collapsed Evidence, and an escaped safe diff only for `proposal-ready`.
- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py' -v`; expect PASS.
- [ ] Commit `feat(github): publish validated city docs reviews`.

### Task 4: Connect the isolated worker to the TechDocs adapter and dogfood

**Files:**
- Modify: `github/scripts/github_intake_docs_patch_worker.py`
- Modify: `github/scripts/github_intake_docs_patch_queue_worker.py`
- Modify: `github/tests/test_github_intake_docs_patch_worker.py`
- Modify: `github/tests/test_github_intake_docs_patch_queue_worker.py`
- Modify: `github/README.md`
- Modify: `../gascity-compose/compose.yaml`
- Modify: `../gascity-compose/scripts/tests/test_github_docs_impact.sh`

- [ ] Write failing tests showing the worker consumes only an assignment, emits only a TechDocs review candidate, and writes no artifact when the agent is unavailable.

```python
def test_unavailable_agent_produces_no_artifact(self):
    self.assertEqual(run_worker(valid_assignment(), agent_available=False)["status"], "unavailable")
    self.assertFalse(self.artifact_path.exists())
```

- [ ] Run worker tests; expect failure because the current worker synthesizes deterministic patch output.
- [ ] Replace deterministic generation with the configured City TechDocs adapter. It receives only the assignment and vendored TechDocs skill. If no completed agent result exists, it writes no artifact. The trusted sidecar may project an artifact but never invent a verdict. Preserve networkless, credential-free, read-only worker isolation.
- [ ] Document the public contract and unsupported boundary: unavailable agent work means no GitHub check.
- [ ] Run `python3 -m unittest discover -s github/tests -p 'test_*.py' -v && (cd ../gascity-compose && make test)`.
- [ ] Dogfood three PR revisions: docs-only → `no-impact`/ `docs-sufficient`; code plus adequate docs → `docs-sufficient`; code without adequate docs → `docs-change-required`/ `proposal-ready`. For each, verify absent-before-result, correct final check, and no City ID on the run page.
- [ ] Commit pack changes as `feat(github): route docs impact through city techdocs` and compose changes as `feat(compose): run city techdocs docs impact adapter`.

## Plan self-review

- Tasks 1–3 cover artifact provenance, exact revision binding, no-pre-result publishing, terse public output, and private evidence.
- Task 4 preserves isolation and validates the three requested dogfood outcomes.
- No deterministic fallback or undeclared artifact handoff remains.
