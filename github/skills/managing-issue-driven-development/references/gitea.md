# Gitea Tracker Adapter

Use this reference for Gitea issues and pull requests. Prefer an installed Gitea connector/MCP, then `tea`, then the Gitea API. Discover capabilities and server version first; installations vary.

## Capability Check

Required for the active workflow:

| Semantic operation | Gitea primitive | Required when |
|---|---|---|
| Read issue, state, and comments | Issue read/comment listing | Always |
| Append protocol event | Issue comment | Always |
| Create issue | Issue create | Projected graph is non-linear |
| Link dependencies | Markdown issue URLs; native dependency fields optional | Multiple issues exist |
| Read change revision and diff | Pull request read/files/commits | Implementation-bearing issue |
| Explicitly close | Issue state update | Closing |

Do not require labels, projects, milestones, or native dependency APIs. Mirror state there only when the server exposes them reliably.

## Linking and Revisions

Use explicit issue and PR URLs in bodies/comments. Avoid merge keywords or integrations that auto-close issues. Preserve the PR head revision, merge commit, and review evidence as durable links or immutable IDs.

If stacked work was implemented eagerly, refresh/rebase it after prerequisites land. Any changed revision returns the dependent issue to implementation and repeats full independent critique and CI.

## Writes and Retries

Use one Gitea automation identity. Search existing comments for `operation_id` before every retry, serialize issue writes, and re-read after mutation. If the server cannot supply a required read or write, leave the issue open and report the missing capability rather than approximating a gate.

Agents return evidence to the driver; they do not post role-specific comments using the shared identity.

## Closure

Never infer parent closure from child state. After the parent sub-graph is terminal, run and record the parent's own lifecycle. The driver explicitly closes each issue only after a fresh reconciliation and confirms the native state transition.
