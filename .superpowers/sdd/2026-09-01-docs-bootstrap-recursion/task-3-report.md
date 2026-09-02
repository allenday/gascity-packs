# Task 3 Report: Idempotent Bootstrap Projection

## Delivered

- Added `project_actions(root, adapter) -> root` to consume persisted pending
  `create_issue`, `create_bead`, `assign_bead`, `post_root_status`, and
  `create_docs_pr` intents.
- Completion is written only after the adapter returns an adopted or newly
  created resource.  Follow-up bead and assignment intents are appended only
  after their predecessor has completed.
- Projection uses durable action IDs as the external logical IDs.  Replays
  therefore call the adapter with the same identity and do not use webhook
  delivery IDs.
- Corrected terminal status actions so their lifecycle remains `pending` and
  the terminal root state is stored separately as `root_state`.
- Added GitHub App issue primitives that create an opaque logical-ID marker and
  scan existing issues to adopt a marker match after a restart.

## Test coverage

- Persisted intent replay/duplicate delivery creates one issue, bead, and
  assignment.
- Crash after external issue creation leaves the action pending; restart adopts
  the existing logical resource and completes the remaining projection.
- Terminal status and docs-PR action IDs complete once under replay.
- GitHub issue marker creation and adoption are covered directly.

## Verification

`python3 -m unittest github.tests.test_github_docs_bootstrap github.tests.test_github_intake_common -v`

- 62 tests passed.

`python3 -m unittest discover -s github/tests -p 'test_*.py' -v`

- 205 tests passed.

`git diff --check`

- Passed.

## Scope and concerns

- No GitHub mutation, author-branch write, merge, formula, or worker work was
  performed.
- The controller remains projection-only: deployment code supplies its
  GitHub/City adapter.  The GitHub helper now provides the stable issue
  adoption primitive that adapter requires.

## Debt-action amendment (2026-09-02)

- Added projection support for Task 2's durable `create_debt_issue` action.
  It resolves the persisted debt by `debt_key`, passes the stable action ID to
  `adapter.create_debt_issue`, and records completion after adoption/creation.
- Debt projection does not append or invoke issue-work, bead, assignment,
  docs-PR, or branch adapters.  A replay test proves it creates/adopts one
  debt issue while every active-work adapter remains unused.

### Amendment verification

`python3 -m unittest github.tests.test_github_docs_bootstrap github.tests.test_github_intake_common -v`

- 67 tests passed.

## Review remediation (2026-09-02)

- Added `FileBootstrapStore`, `project_persisted_root`, and
  `project_configured_root`: production callers now load a durable root under
  a per-root file lock and atomically save it after each projected action.
- Added `GitHubCityBootstrapAdapter`, which obtains a configured GitHub App
  installation token for issue/debt projection and uses the existing City
  Bead command helpers for bead creation and assignment.  Its documentation
  PR path accepts only an explicit `gas-city/` branch; it never writes an
  author branch or merges.
- Hardened issue adoption: marker matches are ignored when the resource is a
  pull request or the author is not the configured GitHub App bot.
- Controller wording now makes the graph boundary explicit: non-blocking debt
  is an inactive leaf with no descendants; only an explicit blocking journey
  edge may continue active work.

### Remediation verification

`python3 -m unittest github.tests.test_github_docs_bootstrap github.tests.test_github_intake_common -v`

- 70 tests passed.
