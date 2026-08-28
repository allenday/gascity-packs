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


class DocsPatchTests(unittest.TestCase):
    def test_validate_has_deterministic_canonical_digest(self) -> None:
        artifact = proposal()
        reversed_artifact = copy.deepcopy(artifact)
        reversed_artifact["files"] = list(reversed(reversed_artifact["files"]))

        first = docs_patch.validate_artifact(artifact)
        second = docs_patch.validate_artifact(reversed_artifact)

        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["patch_sha256"], hashlib.sha256(DIFF.encode("utf-8")).hexdigest())

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

    def test_validate_rejects_claim_without_immutable_evidence(self) -> None:
        artifact = proposal()
        artifact["claims"] = [{"claim": "A material claim.", "evidence": "", "release_scope": "unreleased"}]

        with self.assertRaisesRegex(ValueError, "evidence"):
            docs_patch.validate_artifact(artifact)

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
