# GitHub Documentation Recursion Direct Child

This is the dedicated `docs-recursion-direct-child` City worker. It is not the
legacy `docs-journey` worker and must never emit a
`github-docs-journey-child-update`.

Read and apply this pack's vendored
`skills/developer-experience-techdocs/SKILL.md` for documentation judgment.
It decides what documentation content is useful for the supplied reader
journey; the transport and authority rules below remain mandatory.

Use the local `bd` CLI to locate the single in-progress Bead assigned to this
session and read it with `bd show <bead-id> --json`. Require its
`github.docs_direct_child` metadata value to be the complete Pack-issued
`admitted_child` record from a persisted v3 recursion. If there is not exactly
one such assigned Bead, stop without changing repository state or closing any
Bead. Do not take child input from prose, a transcript, or a legacy journey
record.

Also require `github.docs_direct_child.patch_context` to be the complete
Pack-issued `github-docs-recursion-direct-patch-context` record. It contains
the immutable `proposal_identity` needed for the patch artifact. Echo that
record exactly in `patch_context`; do not infer its base SHA, base ref, or head
repository fields.

Echo that record exactly in `admitted_child`. Do not construct or infer a
recursion identity, child key, budget, classification, or provenance field.
Also require one `github.docs_direct_child.snapshot` metadata value. It names
the read-only exact source snapshot supplied by the controller, including its
head SHA, tree SHA, and local path. Verify that the checked-out snapshot is at
that exact head before editing. Make documentation-only edits in a disposable
copy of that snapshot, then use Git's diff command to generate the patch from
those edits. Do not type or assemble a diff by hand. Never modify the supplied
snapshot, create a branch, commit, push, open or merge a pull request, create
a GitHub issue, or create another child.

Construct exactly one compact JSON object:

```json
{"schema_version":1,"kind":"github-docs-recursion-direct-child-update","admitted_child":{},"state":"complete | blocked | failed | cancelled","patch_context":{},"documentation_patch":{"schema_version":1,"status":"proposed","generated_at":"RFC3339","identity":{},"patch_sha256":"SHA-256","diff":"Git-derived documentation-only diff","files":[],"claims":[],"checks":[]}}
```

For `complete`, `documentation_patch` must be the complete bounded patch
artifact for the exact supplied snapshot. Its identity must preserve the
repository, PR, base SHA, head SHA, head repository, and base ref from
`patch_context.proposal_identity`; its patch SHA must be the SHA-256 of the Git-derived diff; and its
files may name only documentation paths. For `blocked`, `failed`, or
`cancelled`, it must be `null`. Do not add an IDD update, a branch claim, or
any other legacy docs-journey field.

Persist the compact object on the same Bead under the exact metadata key
`github.docs_direct_child.result`. For example, after producing and validating
`RESULT_JSON`, run:

```sh
bd update "$BEAD_ID" --set-metadata "github.docs_direct_child.result=$RESULT_JSON"
```

Re-read the Bead with `bd show "$BEAD_ID" --json` and verify that parsing
`github.docs_direct_child.result` yields the exact object you produced. Only
after that read-back succeeds may you run `bd close "$BEAD_ID"`. If the write
or read-back fails, do not close the Bead. Your final response is not the
durable result; the metadata write is the only result transport accepted by
the City controller.

The trusted City/App controller combines the unchanged Pack-issued
`admission` with the parsed `github.docs_direct_child.result` as exactly
`{"admission": ..., "update": ...}`. It then invokes the Pack completion
boundary:

`scripts/github_intake_docs_direct_child_complete.py --once --input <strict-json>`.

The worker does not call that boundary or require the Pack state directory or
GitHub credentials. The boundary validates the echoed full provenance, patch
schema, digest, documentation-only scope, and snapshot applicability. Only
the trusted GitHub App then applies the patch, commits, pushes, and verifies
the derived `gas-city/docs-...` branch before the controller projects the sole
follow-up PR.
