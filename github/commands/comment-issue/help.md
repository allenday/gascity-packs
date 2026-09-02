Post an issue comment using the workspace-owned GitHub App installation.

Examples:
  gc github comment-issue owner/repo 42 \
    --installation-id 123456 \
    --github-app-identity mayor \
    --body "Started work on this issue"

  gc github comment-issue owner/repo 42 \
    --installation-id 123456 \
    --body-file ./comment.md

  printf '%s\n' "Started work on this issue" | \
    gc github comment-issue owner/repo 42 \
      --installation-id 123456 \
      --body-stdin

Arguments:
  <repository>   owner/repo
  <issue-number> GitHub issue number

Flags:
  --installation-id <id>          GitHub App installation id, unless identity resolves one
  --github-app-identity <identity>     GitHub App identity for the comment author; see docs/github-app-identity.md
  --body <text>                   inline markdown body
  --body-file <path>              read markdown body from file
  --body-stdin                    read markdown body from standard input
