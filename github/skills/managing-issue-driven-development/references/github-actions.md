# GitHub Actions CI Adapter

Use this reference when required CI runs in GitHub Actions. Prefer an installed GitHub connector/MCP, then `gh`, then the Actions API. Discover available operations before acting.

## Evidence Contract

For the issue's exact current revision, collect:

- workflow and run URL/ID;
- immutable commit SHA;
- conclusion of every required check or job;
- attempt number and timestamps;
- relevant failing step/log evidence when not green.

Required checks come from repository policy, branch protection/rulesets, the issue plan, and newly discovered acceptance risks. Do not equate one green workflow with all required CI.

## Failure Loop

Any failing required run returns the issue to `implementation` and invalidates critique, CI, acceptance, and readiness. Use `superpowers:systematic-debugging` to diagnose. After a fix—or a no-change rerun following investigation—obtain a new full independent critique, then run required CI again. A partial delta review, prior approval, or “flaky test” label is not a waiver.

Rerun only the smallest provider-supported scope that still proves all required checks, but record every attempt. Do not erase or replace the failed-run evidence.

## Staleness

Treat CI as stale when the PR head, workflow/configuration, base integration state, or resolved dependency set changes materially. Refresh checks on the final relevant revision before acceptance or closure.

## Separation From Acceptance

A green Actions result advances `ci → acceptance`; it does not advance directly to readiness. Record issue-level acceptance validation separately.
