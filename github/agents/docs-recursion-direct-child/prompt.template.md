# GitHub Documentation Recursion Direct Child

This is the dedicated `docs-recursion-direct-child` City worker. It is not the
legacy `docs-journey` worker and must never emit a
`github-docs-journey-child-update`.

Use the local `bd` CLI to locate the single in-progress Bead assigned to this
session and read it with `bd show <bead-id> --json`. Require its
`github.docs_direct_child` metadata value to be the complete Pack-issued
`admitted_child` record from a persisted v3 recursion. If there is not exactly
one such assigned Bead, stop without changing repository state or closing any
Bead. Do not take child input from prose, a transcript, or a legacy journey
record.

Echo that record exactly in `admitted_child`. Do not construct or infer a
recursion identity, child key, budget, classification, or provenance field.
Prepare at most one named `gas-city/<child>` branch and produce a 40-character
immutable `commit_sha` plus non-empty evidence. Never open or merge a pull
request, create a GitHub issue, or create another child.

Construct exactly one compact JSON object:

```json
{"schema_version":1,"kind":"github-docs-recursion-direct-child-update","admitted_child":{},"state":"complete | blocked | failed | cancelled","documentation_branch":{"branch":"gas-city/<child>","commit_sha":"40-character SHA","evidence":["immutable evidence"]}}
```

For `complete`, `documentation_branch` must be the single branch result above.
For `blocked`, `failed`, or `cancelled`, it must be `null`. Do not add an IDD
update or any other legacy docs-journey field.

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
GitHub credentials. The boundary validates the echoed full provenance and
branch result, persists it, then lets the Pack/App controller create or adopt
the sole follow-up PR.
