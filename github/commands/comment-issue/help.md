Post an issue comment using the workspace-owned GitHub App installation.

Example:
  gc github comment-issue owner/repo 42 \
    --installation-id 123456 \
    --github-app-identity mayor \
    --body "Started work on this issue"

Preview a comment request without loading GitHub App configuration or posting:

  gc github comment-issue owner/repo 42 \
    --body "Started work on this issue" \
    --dry-run

Arguments:
  <repository>   owner/repo
  <issue-number> GitHub issue number

Flags:
  --installation-id <id>          GitHub App installation id, unless identity resolves one
  --github-app-identity <identity>     GitHub App identity for the comment author; see docs/github-app-identity.md
  --body <text>                   inline markdown body
  --body-file <path>              read markdown body from file
  --body-stdin                    read markdown body from standard input
  --dry-run                       print the resolved request without posting a comment
