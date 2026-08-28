# Task 2 report — Queue docs impact for City review

## Status

Implemented in commit `feat(github): queue docs impact for city review`.

## Changes

- Replaced deterministic path classification and all pre-result Check Run publication with a revision-bound TechDocs assignment queue.
- Added `queue_agent_review`, which writes one sanitized descriptor per immutable PR source key to the existing snapshot inbox. The descriptor contains the exact PR identity, source key, changed paths, and the required `developer-experience-techdocs` skill.
- Duplicate deliveries reuse the existing assignment; a distinct head SHA receives a different assignment path.
- Added tests for the absent-before-result GitHub boundary and durable assignment identity/reuse behavior.

## Verification

- RED: `python3 -m unittest github.tests.test_github_intake_docs_impact github.tests.test_github_intake_service -v` failed before implementation because the old evaluator created a check and `queue_agent_review` did not exist.
- `python3 -m unittest github.tests.test_github_intake_docs_impact github.tests.test_github_intake_service -v` — PASS (63 tests).
- `python3 -m unittest github.tests.test_github_intake_docs_impact github.tests.test_github_intake_service github.tests.test_github_intake_docs_impact_pipeline github.tests.test_github_intake_docs_patch_queue_worker -v` — PASS (70 tests).
- `python3 -m unittest discover -s github/tests -p 'test_*.py' -v` — PASS (150 tests).
- `git diff --check` — PASS.

## Concerns

The legacy patch sidecar remains present for the following task to replace, but this evaluator ignores its candidate artifacts and cannot create or update a GitHub check before a City agent review exists.
