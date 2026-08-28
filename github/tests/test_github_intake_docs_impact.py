from __future__ import annotations

import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_impact as docs_impact
import github_intake_service as service


DIFF = """diff --git a/docs/guide.md b/docs/guide.md
index 1111111..2222222 100644
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-Old guidance.
+New guidance.
"""


def proposal(head_sha: str = "a" * 40, status: str = "proposed") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "generated_at": "2026-08-28T12:00:00Z",
        "identity": {
            "repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
            "base_sha": "b" * 40, "head_sha": head_sha,
            "head_repository_id": "17", "head_repository": "allenday/demo", "base_ref": "main",
        },
        "patch_sha256": hashlib.sha256(DIFF.encode("utf-8")).hexdigest(), "diff": DIFF,
        "files": [{"path": "docs/guide.md", "sha256": "c" * 64}],
        "claims": [{"claim": "The guide documents the new workflow.",
                    "evidence": "github://allenday/demo/blob/" + head_sha + "/README.md",
                    "release_scope": "unreleased"}],
        "checks": [{"command": "make docs-check", "status": "passed", "explanation": "Documentation checks passed."}],
    }


class DocsImpactTests(unittest.TestCase):
    def test_derived_result_is_idempotent_and_persists_canonical_artifact(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        artifact = docs_impact.docs_patch.validate_artifact(proposal())
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict("os.environ", {"GC_SERVICE_STATE_ROOT": state_root}), mock.patch.object(
            service, "addressed_sources_by_key", side_effect=[[], [{"id": "ga-result"}]]
        ), mock.patch.object(service, "run_subprocess", return_value=mock.Mock(returncode=0, stdout='{"id":"ga-result"}', stderr="")):
            created = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, artifact)
            duplicate = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, artifact)

            self.assertEqual(created["status"], "created")
            self.assertEqual(duplicate, {**created, "status": "duplicate", "reason": "source_key_exists"})
            self.assertEqual(service.github_pr_docs_patch_key(context, created["artifact_sha256"]), created["source_key"])
            self.assertEqual(service.common.read_json(created["artifact_path"])["artifact_sha256"], created["artifact_sha256"])

    def test_projection_rejects_artifact_for_an_older_source_sha(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "b" * 40}
        result = docs_impact.project_docs_patch(context, {"bead_id": "ga-source"}, proposal())

        self.assertEqual(result["outcome"], "unavailable")
        self.assertEqual(result["reason"], "artifact_identity_mismatch")
        self.assertIsNone(result["result"])

    def test_proposed_projection_has_safe_actionable_check_text(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        artifact = docs_impact.docs_patch.validate_artifact(proposal())
        output = docs_impact.patch_check_output(context, {"bead_id": "ga-source"}, artifact, "proposed")

        self.assertEqual(output["title"], "Documentation update proposed")
        self.assertIn("Artifact digest:", output["summary"])
        self.assertIn("Apply this documentation patch", output["summary"])
        self.assertIn("```diff", output["text"])
        self.assertIn("docs/guide.md", output["text"])

    def test_unavailable_artifact_has_action_required_output_without_patch_text(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        result = docs_impact.project_docs_patch(context, {"bead_id": "ga-source"}, None)
        output = docs_impact.patch_check_output(context, {"bead_id": "ga-source"}, None, result["outcome"])

        self.assertEqual(result["outcome"], "unavailable")
        self.assertEqual(result["reason"], "artifact_unavailable")
        self.assertEqual(output["title"], "Documentation proposal unavailable")
        self.assertNotIn("```diff", output.get("text", ""))

    def test_webhook_payload_unwraps_durable_delivery_envelope(self) -> None:
        payload = {"number": 9, "pull_request": {"head": {"sha": "a" * 40}}}
        self.assertEqual(docs_impact.webhook_payload({"event": "pull_request", "payload": payload}), payload)

    def test_classify_paths_is_conservative_for_product_change_without_docs(self) -> None:
        self.assertEqual(
            docs_impact.classify_paths(["github/scripts/github_intake_common.py", "github/tests/test_common.py"])[0],
            "needs-human-decision",
        )

    def test_classify_paths_passes_non_product_change(self) -> None:
        self.assertEqual(docs_impact.classify_paths([".github/workflows/test.yml"])[0], "no-impact")

    def test_evaluate_completes_unavailable_check_as_action_required_for_exact_revision(self) -> None:
        payload = {
            "repository": {"id": 17, "full_name": "allenday/demo", "name": "demo", "owner": {"login": "allenday"}},
            "pull_request": {"number": 9, "html_url": "https://github.com/allenday/demo/pull/9", "head": {"sha": "a" * 40}},
            "installation": {"id": 44},
        }
        with mock.patch.object(docs_impact, "create_source", return_value={"status": "created", "bead_id": "ga-1"}), mock.patch.object(
            docs_impact.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check, mock.patch.object(
            docs_impact.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "action_required"}
        ) as update_check:
            result = docs_impact.evaluate(payload, "delivery-1", "token")

        self.assertEqual(result["outcome"], "unavailable")
        self.assertEqual(create_check.call_args.args[3], "a" * 40)
        self.assertEqual(update_check.call_args.args[3], 81)
        self.assertEqual(update_check.call_args.args[5], "action_required")
