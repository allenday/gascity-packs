# Task 4 report — explicit-root formula and worker contract

## Status

Completed the explicit-root formula, its opt-in documentation, and the
`docs-bootstrap` worker contract. No GitHub mutation, plan-ledger edit, or
controller behavior change was made.

## Delivered surface

- `github/formulas/github-docs-bootstrap.formula.toml` requires an explicit
  root identity, immutable default-branch SHA, full `techdocs` reader journey,
  and every controller budget. Its lifecycle is load root, snapshot/admit,
  project, run admitted child, reconcile, and terminal status.
- `github/agents/docs-bootstrap/` adds a rig-scoped, non-fallback worker. It
  accepts only one admitted child record, preserves qualified provenance in an
  IDD-compliant child update, and can create at most one App-owned
  documentation pull request. It cannot write a contributor branch or merge.
- `github/README.md` documents the explicit opt-in command, prerequisites,
  budgets, terminal states, and the non-goal for ordinary pull-request checks.
- `github/tests/test_github_docs_bootstrap_formula.py` protects the explicit
  root, journey, budget, provenance, lifecycle, and write-authority boundary.

## TDD evidence

The new focused test module was run before implementation and failed because
the formula and worker artifacts did not yet exist. After implementation, its
five tests pass.

## Validation

- `python3 -m unittest github/tests/test_github_docs_bootstrap_formula.py -v`
  — 5 passed
- `python3 -m unittest discover -s github/tests -v` — 224 passed
- TOML parsed successfully for `github/pack.toml`, the new formula, and the
  worker metadata.
- `git diff --check` passed.

## Concerns

The formula is deliberately a contract surface over the durable controller
implemented by Task 3. It does not add an event rule or a new service, so no
ordinary pull-request documentation workflow can dispatch bootstrap work.

## Review follow-up

Strengthened the formula contract tests after review. Required reader-journey
and budget variables now fail the test contract if they gain a default. The
formula declares the only supported reader-journey domain (`techdocs`) and
backfill values (`blocking-only`, `record-debt`); negative mutations prove
that other values are rejected. The worker prompt now carries a
machine-readable authority contract, with negative mutations covering author
and contributor branch writes, any merge authority, a second documentation
pull request, and a non-App pull-request owner.

## Review follow-up correction

Removed the formula's fixed `techdocs` domain and backfill-policy allowlist:
the formula requires every supplied journey value without defaults, while the
durable controller owns supported-value validation. Replaced the auxiliary
machine-readable worker authority block with tests that read and mutate the
operative prompt prose itself. Those mutations prove the prompt rejects
author/contributor branch writes, merges, a second documentation pull request,
and a non-App-owned documentation pull request.
