# Task 2 Report: Bootstrap Durable Model

## Changed files

- `github/scripts/github_docs_bootstrap.py`
- `github/tests/test_github_docs_bootstrap.py`

## Red

Command:

```sh
python3 -m unittest github.tests.test_github_docs_bootstrap -v
```

Output: the test module failed to import with
`ModuleNotFoundError: No module named 'github_docs_bootstrap'`. This confirmed
the tests exercised the required new public interface before its implementation
existed.

## Green

The pure controller now builds serialization-safe explicit-root records,
computes the exact immutable root identity, normalizes evidence paths, and
hashes the root identity, exact decision identity, and paths into each child
key. Admission treats TechDocs rationale as opaque and only carries the
producer's exact machine verdict and provenance forward. It writes only
durable action intents; it has no GitHub, City, process, queue, or network
client.

The state transitions enforce duplicate adoption, visited-surface suppression,
snapshot mismatch escalation, depth/child/docs-PR/elapsed/non-progress
budgets, product ambiguity, and the five allowed terminal states. Reconciliation
re-emits pending persisted actions without projecting them.

Focused command:

```sh
python3 -m unittest github.tests.test_github_docs_bootstrap -v
```

Output: 10 tests passed.

## Final verification

```sh
python3 -m unittest discover -s github/tests -p 'test_*.py'
git diff --check
```

Output: the full GitHub suite ran 197 tests and passed; the whitespace check
exited successfully.

## Commit

`feat(github): add bounded docs bootstrap model`

## Self-review

- Root creation rejects implicit roots and records all specified defaults.
- No decision rationale is parsed or reinterpreted; only bounded provenance
  and machine fields drive admission.
- The root and child values consist only of JSON-serializable primitives,
  lists, and dictionaries.
- This task contains no Task 3 projection adapter, GitHub mutation, City
  mutation, worker, formula, or ordinary PR trigger.

## Concerns

Task 3 must mark action records complete after it projects them and must own
the external issue/bead/PR adapter semantics. This model intentionally leaves
those side effects absent.

## Review-fix follow-up

Review found that the first implementation accepted a hand-selected subset of
the docs-impact artifact and evaluated ambiguity/snapshot flags before proving
the artifact. That let malformed or foreign input influence terminal state.

New adversarial tests were written first for wrong kind/schema, foreign
repository provenance, arbitrary source keys, malformed evidence, invalid
ambiguity input, and changed canonical decision identity. Before the fix they
failed: valid established artifacts did not use the previous private shape,
and malformed inputs carrying ambiguity terminalized the root.

The controller now validates a complete established
`github-pr-docs-impact-review` through `validate_agent_review` before it
derives any controller field. It accepts an optional small controller envelope
only for `artifact`, `product_ambiguity`, and `depth`; all other envelope
fields are rejected. The canonical `review_sha256`, which binds the entire
validated artifact including its identity and provenance, is part of the
child-key input. Only a validated artifact for the root repository may then
cause product-decision or stale-snapshot terminalization.

The root additionally normalizes and deduplicates validated evidence paths
before storing visited surfaces or hashing the child key; the canonical review
digest still binds the complete unmodified validated decision.

Verification:

```sh
python3 -m unittest github.tests.test_github_docs_bootstrap -v
python3 -m unittest discover -s github/tests -p 'test_*.py'
git diff --check
```

Output: focused suite 12/12; full GitHub suite 199/199; whitespace check
passed.
