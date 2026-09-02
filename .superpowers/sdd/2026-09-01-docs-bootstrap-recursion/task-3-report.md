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

## Scoped re-review remediation (2026-09-02)

- Added `github_intake_docs_bootstrap_commands.py project --once`, the
  production entrypoint for one stored root.  It invokes
  `project_configured_root`, which locks, loads, reconciles, saves, and
  projects the root with the configured authenticated adapter.
- Bead adoption no longer calls the ambient-root helper.  It now uses the
  adapter's `self.city_root` for its `gc bd list` lookup as well as creation
  and assignment, so a restart cannot search a different City namespace.
- Added coverage for the entrypoint and for a persisted restart with divergent
  ambient/configured City roots.

## Non-progress remediation (2026-09-02)

- `project_configured_root` now projects persisted pending actions before
  reconciliation.  A successful projection resets `non_progress_count`; only
  a reconciliation pass with no projectable action can consume the retry
  budget.  Deadline and terminal reconciliation remain in the no-pending path.
- Added staged issue → bead → assignment coverage proving normal successful
  passes remain active and leave the non-progress budget at zero.

## Pending-retry and terminal-preflight remediation (2026-09-02)

- Configured projection now evaluates terminal conditions before dispatching a
  persisted external action.  A cancelled, stale, owner-review, deadline, or
  budget-terminal root is saved as terminal and performs no pending adapter
  call.
- A failed pending adapter projection is reconciled and saved as a durable
  no-progress retry. Repeated failures increment `non_progress_count` and
  terminalize at the configured limit, while successful staged successors
  still reset the counter.
- Added coverage for repeated adapter failures through budget exhaustion and
  for an owner-review terminal change while an issue action remains pending.

### Remediation verification

`python3 -m unittest github.tests.test_github_docs_bootstrap github.tests.test_github_docs_bootstrap_commands github.tests.test_github_intake_common -v`

- 75 tests passed.
