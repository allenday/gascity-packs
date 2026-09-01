# Woodpecker CI Adapter

Use this reference when required CI runs in Woodpecker. Prefer an installed connector/MCP, then the Woodpecker CLI/API supported by the deployment. Discover server version, repository identity, and callable operations first.

## Evidence Contract

For the issue's exact current revision, collect:

- repository and pipeline/run URL or stable ID;
- immutable commit SHA and event/ref;
- pipeline status plus required step statuses;
- attempt/run number and timestamps;
- relevant failing step/log evidence when not green.

Derive required pipelines and steps from repository policy and the issue plan. A successful optional pipeline is not proof that required CI passed.

## Failure Loop

Any required failure returns the issue to `implementation` and invalidates critique, CI, acceptance, and readiness. Diagnose with `superpowers:systematic-debugging`. Whether the repair changes code, pipeline configuration, infrastructure, or only triggers a rerun, repeat full independent critique before accepting new CI evidence. Deadlines and suspected flakes create no waiver.

Preserve failed-run links. If retrying an API action yields an ambiguous result, list runs for the revision and reconcile by stable run identity before triggering another attempt.

## Staleness

Treat evidence as stale when the commit, pipeline configuration, target integration state, or resolved dependencies change materially. Re-run on the final relevant revision before acceptance or closure.

## Separation From Acceptance

Green Woodpecker pipelines advance `ci → acceptance` only. The driver separately validates and records the issue's intended outcome.
