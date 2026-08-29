from __future__ import annotations

import copy
import hashlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_patch as docs_patch


DIFF = """diff --git a/docs/guide.md b/docs/guide.md
index 1111111..2222222 100644
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-Old guidance.
+New guidance.
"""

MULTI_DIFF = """diff --git a/docs/guide.md b/docs/guide.md
index 1111111..2222222 100644
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-Old guidance.
+New guidance.
diff --git a/docs/install.md b/docs/install.md
index 3333333..4444444 100644
--- a/docs/install.md
+++ b/docs/install.md
@@ -1 +1 @@
-Old install.
+New install.
"""


def proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "proposed",
        "generated_at": "2026-08-28T12:00:00Z",
        "identity": {
            "repository_id": "17",
            "repository": "allenday/demo",
            "pr_number": 9,
            "base_sha": "b" * 40,
            "head_sha": "a" * 40,
            "head_repository_id": "17",
            "head_repository": "allenday/demo",
            "base_ref": "main",
        },
        "patch_sha256": hashlib.sha256(DIFF.encode("utf-8")).hexdigest(),
        "diff": DIFF,
        "files": [{"path": "docs/guide.md", "sha256": "c" * 64}],
        "claims": [{
            "claim": "The guide documents the new workflow.",
            "evidence": "github://allenday/demo/blob/" + "a" * 40 + "/README.md",
            "release_scope": "unreleased",
        }],
        "checks": [{"command": "make docs-check", "status": "passed", "explanation": "Documentation checks passed."}],
    }


def valid_agent_review() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-review",
        "identity": {
            "repository_id": "17",
            "repository": "allenday/demo",
            "pr_number": 9,
            "head_sha": "a" * 40,
            "source_key": "github-pr:17:9:" + "a" * 40,
        },
        "agent_skill": "developer-experience-techdocs",
        "verdict": "docs-sufficient",
        "rationale": "The changed behavior is adequately documented.",
        "evidence": [
            {"path": "docs/guide.md", "evidence": "github://allenday/demo/blob/" + "a" * 40 + "/docs/guide.md"}
        ],
        "confidence": 0.92,
        "proposal": None,
    }


class DocsPatchTests(unittest.TestCase):
    def test_validate_agent_review_returns_revision_bound_normalized_digest(self) -> None:
        review = docs_patch.validate_agent_review(valid_agent_review())
        self.assertEqual(review["kind"], "github-pr-docs-impact-review")
        self.assertEqual(review["identity"]["source_key"], "github-pr:17:9:" + "a" * 40)
        self.assertRegex(review["review_sha256"], r"^[0-9a-f]{64}$")

    def test_validate_agent_review_rejects_unbound_result(self) -> None:
        review = valid_agent_review()
        review["identity"].pop("source_key")
        with self.assertRaises(ValueError):
            docs_patch.validate_agent_review(review)

    def test_validate_agent_review_rejects_boolean_pr_number(self) -> None:
        review = valid_agent_review()
        review["identity"]["pr_number"] = True
        review["identity"]["source_key"] = "github-pr:17:True:" + "a" * 40
        with self.assertRaises(ValueError):
            docs_patch.validate_agent_review(review)

    def test_validate_agent_review_rejects_unknown_verdict(self) -> None:
        review = valid_agent_review()
        review["verdict"] = "maybe"
        with self.assertRaisesRegex(ValueError, "verdict"):
            docs_patch.validate_agent_review(review)

    def test_validate_agent_review_rejects_empty_rationale(self) -> None:
        review = valid_agent_review()
        review["rationale"] = "  "
        with self.assertRaisesRegex(ValueError, "rationale"):
            docs_patch.validate_agent_review(review)

    def test_validate_agent_review_rejects_malformed_evidence(self) -> None:
        review = valid_agent_review()
        review["evidence"] = [{"path": "docs/guide.md", "evidence": "latest"}]
        with self.assertRaisesRegex(ValueError, "evidence"):
            docs_patch.validate_agent_review(review)

    def test_validate_agent_review_allows_proposal_only_for_proposal_ready(self) -> None:
        review = valid_agent_review()
        review["proposal"] = proposal()
        with self.assertRaisesRegex(ValueError, "proposal"):
            docs_patch.validate_agent_review(review)

        review["verdict"] = "proposal-ready"
        validated = docs_patch.validate_agent_review(review)
        self.assertIsNotNone(validated["proposal"])

    def test_validate_has_deterministic_canonical_digest(self) -> None:
        artifact = proposal()
        reversed_artifact = copy.deepcopy(artifact)
        reversed_artifact["files"] = list(reversed(reversed_artifact["files"]))

        first = docs_patch.validate_artifact(artifact)
        second = docs_patch.validate_artifact(reversed_artifact)

        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["patch_sha256"], hashlib.sha256(DIFF.encode("utf-8")).hexdigest())

    def test_validate_canonicalizes_multi_item_ledger_ordering(self) -> None:
        artifact = proposal()
        artifact["diff"] = MULTI_DIFF
        artifact["patch_sha256"] = hashlib.sha256(MULTI_DIFF.encode("utf-8")).hexdigest()
        artifact["files"] = [
            {"path": "docs/install.md", "sha256": "d" * 64},
            {"path": "docs/guide.md", "sha256": "c" * 64},
        ]
        artifact["claims"] = [
            {"claim": "Install instructions changed.", "evidence": "git:" + "b" * 40, "release_scope": "unreleased"},
            artifact["claims"][0],
        ]
        artifact["checks"] = [
            {"command": "make link-check", "status": "passed", "explanation": "Links passed."},
            artifact["checks"][0],
        ]
        reordered = copy.deepcopy(artifact)
        for field in ("files", "claims", "checks"):
            reordered[field] = list(reversed(reordered[field]))

        self.assertEqual(
            docs_patch.validate_artifact(artifact)["artifact_sha256"],
            docs_patch.validate_artifact(reordered)["artifact_sha256"],
        )

    def test_validate_rejects_traversal_and_non_documentation_paths(self) -> None:
        for path in ("../docs/escape.md", "/docs/absolute.md", "src/app.py"):
            with self.subTest(path=path):
                artifact = proposal()
                artifact["files"] = [{"path": path, "sha256": "c" * 64}]
                artifact["diff"] = DIFF.replace("docs/guide.md", path)
                artifact["patch_sha256"] = hashlib.sha256(artifact["diff"].encode("utf-8")).hexdigest()
                with self.assertRaisesRegex(ValueError, "path"):
                    docs_patch.validate_artifact(artifact)

    def test_validate_rejects_binary_and_oversized_diffs(self) -> None:
        binary = proposal()
        binary["diff"] = "diff --git a/docs/guide.md b/docs/guide.md\nBinary files differ\n"
        binary["patch_sha256"] = hashlib.sha256(binary["diff"].encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "binary"):
            docs_patch.validate_artifact(binary)

        oversized = proposal()
        oversized["diff"] = DIFF + ("x" * (docs_patch.MAX_DIFF_BYTES + 1))
        oversized["patch_sha256"] = hashlib.sha256(oversized["diff"].encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "too large"):
            docs_patch.validate_artifact(oversized)

    def test_validate_rejects_unsafe_unified_diff_body_paths(self) -> None:
        artifact = proposal()
        artifact["diff"] = DIFF.replace("--- a/docs/guide.md", "--- a/src/app.py").replace(
            "+++ b/docs/guide.md", "+++ b/src/app.py"
        )
        artifact["patch_sha256"] = hashlib.sha256(artifact["diff"].encode("utf-8")).hexdigest()

        with self.assertRaisesRegex(ValueError, "path"):
            docs_patch.validate_artifact(artifact)

    def test_validate_rejects_claim_without_immutable_evidence(self) -> None:
        artifact = proposal()
        artifact["claims"] = [{"claim": "A material claim.", "evidence": "", "release_scope": "unreleased"}]

        with self.assertRaisesRegex(ValueError, "evidence"):
            docs_patch.validate_artifact(artifact)

    def test_validate_rejects_git_branch_evidence(self) -> None:
        artifact = proposal()
        artifact["claims"][0]["evidence"] = "git:main"

        with self.assertRaisesRegex(ValueError, "commit SHA"):
            docs_patch.validate_artifact(artifact)

    def test_validate_requires_timezone_in_generation_time(self) -> None:
        artifact = proposal()
        artifact["generated_at"] = "2026-08-28T12:00:00"

        with self.assertRaisesRegex(ValueError, "RFC3339"):
            docs_patch.validate_artifact(artifact)

    def test_validate_accepts_and_revalidates_artifact_digest(self) -> None:
        validated = docs_patch.validate_artifact(proposal())

        revalidated = docs_patch.validate_artifact(validated)
        self.assertEqual(revalidated["artifact_sha256"], validated["artifact_sha256"])

        validated["artifact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "artifact_sha256"):
            docs_patch.validate_artifact(validated)

    def test_validate_redacts_secrets_from_persisted_fields(self) -> None:
        artifact = proposal()
        artifact["claims"][0]["claim"] = "Use token ghp_abcdefghijklmnopqrstuvwxyz1234567890 now."
        artifact["checks"][0]["explanation"] = "Authorization: Bearer top-secret-value"

        validated = docs_patch.validate_artifact(artifact)
        serialized = docs_patch.canonical_json(validated)

        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz1234567890", serialized)
        self.assertNotIn("top-secret-value", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_validate_rejects_unknown_schema_fields(self) -> None:
        artifact = proposal()
        artifact["unexpected"] = "not accepted"

        with self.assertRaisesRegex(ValueError, "unexpected"):
            docs_patch.validate_artifact(artifact)


if __name__ == "__main__":
    unittest.main()
