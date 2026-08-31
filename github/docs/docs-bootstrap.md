# Documentation bootstrap contract

Use documentation bootstrap when a repository's default branch has incomplete
or absent developer documentation. It complements, rather than replaces, the
pull-request reviewer: both produce the same durable documentation-gap record.

## Trust and identity

The coordinator resolves the repository default branch once and records its
immutable commit SHA. It builds a bounded, read-only inventory from that
revision. If the inventory is truncated, unavailable, or cannot be bound to
that SHA, it stops without creating a GitHub issue, City bead, branch, or pull
request.

Each accepted gap uses `github-docs-gap.v1` with these stable fields:

- repository id and full name
- default-branch SHA
- affected code surface and bounded evidence paths
- gap classification and rationale
- deterministic gap key

The coordinator persists this record before any external action. GitHub issues,
City beads, and writer pull requests are projections of the record, not the
source of truth.

## Reconciliation

For one gap key, the coordinator records checkpoints for issue creation, City
bead creation, writer dispatch, and follow-up pull request creation. A retry
reads those checkpoints first. It reuses an existing projection when its stable
marker matches the gap key; it never creates a second issue or bead merely
because an earlier request timed out.

The GitHub issue links the immutable baseline revision and the City work item.
The City bead is assigned internally to the bootstrap writer. Neither implies a
GitHub assignment to the App.

## Writer boundary

The writer receives only the accepted gap record and its bounded evidence. It
may create or change documentation files on an App-owned `gas-city/docs-*`
branch and open a normal pull request. It must not write an author branch,
change non-documentation files, or merge any pull request. Human GitHub review
remains the merge gate.

## Dependency interface

Bootstrap uses the durable-dispatch and recovery semantics defined by the docs
PR reviewer lifecycle, but it does not reuse PR Check Run state. It applies the
proposal-authority evidence-completeness gate before every issue, bead, branch,
or PR projection. If those dependencies expose a generic dispatcher adapter,
bootstrap consumes it; otherwise it defines a narrow bootstrap adapter with the
same persisted-before-action and retry semantics.

## Acceptance tests

- An undocumented surface produces one gap record, one linked issue, and one
  internally assigned bead across duplicate deliveries and restart recovery.
- A truncated inventory produces no external projection.
- A writer PR is documentation-only and App-owned.
- A PR-review gap and a bootstrap gap with the same key converge on one
  remediation record.
