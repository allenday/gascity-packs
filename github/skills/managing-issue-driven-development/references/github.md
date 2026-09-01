# GitHub Tracker Adapter

Use this reference for GitHub Issues and pull requests. Prefer an installed GitHub connector/MCP, then `gh`, then the REST/GraphQL API. Discover the callable surface before choosing commands; do not assume a particular tool name.

## Capability Check

Required for the active workflow:

| Semantic operation | GitHub primitive | Required when |
|---|---|---|
| Read issue, state, and comments | Issue read/list comments | Always |
| Append protocol event | Issue comment | Always |
| Create issue | Issue create | Projected graph is non-linear |
| Link dependencies | Markdown issue URLs; native sub-issues optional | Multiple issues exist |
| Read change revision and diff | Pull request read/files/commits | Implementation-bearing issue |
| Explicitly close | Issue state update | Closing |

If native sub-issues, task lists, projects, labels, milestones, or dependency metadata are available, use them only as mirrors of the portable graph and state.

## Linking Without Auto-Close

Use `Refs #123` or an explicit issue URL in PR bodies. Do not use `Fixes`, `Closes`, or `Resolves` keywords: merge-triggered closure bypasses the driver's final reconciliation and acceptance gates.

Record immutable PR head and merge commit identifiers in evidence. A PR approval attached to an earlier head does not satisfy critique for a later head.

## Writes and Retries

Use one GitHub automation identity. Before appending, search comments for the event `operation_id`. After create/comment/edit/close, re-read the target. If a write outcome is ambiguous, reconcile current state before retrying.

Agents may work in branches and return PR/review evidence, but only the driver comments, edits, links, or closes issues.

## Closure

Disable or avoid repository automation that closes these issues merely because a PR merged. The driver appends `ready_to_close`, refreshes issue/PR/CI state, performs the explicit close mutation, and confirms `closed`. Use the protocol's pre-close terminal event fallback if post-close comments are unavailable.
