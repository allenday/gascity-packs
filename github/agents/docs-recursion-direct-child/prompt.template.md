# GitHub Documentation Recursion Direct Child

Your complete input is the complete Pack-issued `admitted_child` record from a
persisted v3 recursion. Echo that record exactly in `admitted_child`. Do not
construct or infer a recursion identity, child key, budget, classification, or
provenance field. Prepare at most one named `gas-city/<child>` branch and return a
40-character immutable `commit_sha` plus non-empty evidence. Never open or
merge a pull request, create a GitHub issue, or create another child.

Return exactly one JSON object:

```json
{"schema_version":1,"kind":"github-docs-recursion-direct-child-update","admitted_child":{},"state":"complete | blocked | failed | cancelled","documentation_branch":{"branch":"gas-city/<child>","commit_sha":"40-character SHA","evidence":["immutable evidence"]}}
```

The Pack completion boundary is
`scripts/github_intake_docs_direct_child_complete.py --once --input <strict-json>`.
Its input carries the unchanged Pack-issued admission record alongside this
update. It validates the echoed full provenance and branch result, persists it, then
lets the Pack/App controller create or adopt the sole follow-up PR.
