# Task 5 report — bounded docs-bootstrap graph smoke

## Status

Completed the bounded end-to-end graph smoke without GitHub mutations or plan
ledger edits.

## Delivered

- Added `github/tests/test_github_docs_bootstrap_smoke.py`, using an in-memory
  GitHub/City adapter to exercise one explicit root through a blocking exact
  `docs-change-required` decision, issue/Bead assignment, a single App-owned
  PR projection, and `baseline-complete` terminalization.
- The smoke also proves that `record-debt` creates at most one debt issue and
  does not emit active work, and that a normal PR review artifact cannot create
  a bootstrap root.
- Added `record_child_update`, which accepts only an already admitted child
  whose worker-supplied provenance matches exactly, and stages at most one
  `gas-city/` documentation PR action.
- Corrected reconciliation precedence so a completed child terminalizes the
  root as `baseline-complete` even when its one permitted PR consumes the
  final PR budget.
- Documented the qualified worker-result boundary in `github/README.md`.

## TDD evidence

The new smoke initially failed with an `ImportError` for the missing
`record_child_update` controller bridge. After adding the bridge, it exposed
the incorrect `budget-exhausted` terminal state; reordering terminal
reconciliation made the smoke pass.

## Verification

- `python3 -m unittest github.tests.test_github_docs_bootstrap_smoke -v` — 3
  passed.
- `python3 -m unittest github.tests.test_github_docs_bootstrap -v` — 28
  passed.
- `python3 -m unittest discover -s github/tests -v` — 228 passed.
- `git diff --check` — passed.

## Concerns

The new child-update bridge is controller-only; formula/runtime orchestration
remains responsible for durably persisting the returned root between worker
completion and projection, preserving the existing persist-before-action
boundary.
