from __future__ import annotations

import hashlib
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_impact as docs_impact
import github_intake_docs_patch as docs_patch
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


def valid_agent_review(head_sha: str = "a" * 40, verdict: str = "docs-sufficient") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-review",
        "identity": {
            "repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
            "head_sha": head_sha, "source_key": "github-pr:17:9:" + head_sha,
        },
        "agent_skill": "developer-experience-techdocs",
        "verdict": verdict,
        "rationale": "The changed behavior is adequately documented.",
        "evidence": [{
            "path": "docs/guide.md",
            "evidence": "github://allenday/demo/blob/" + head_sha + "/docs/guide.md",
        }],
        "confidence": 0.92,
        "proposal": proposal(head_sha) if verdict == "proposal-ready" else None,
    }


class DocsImpactTests(unittest.TestCase):
    def test_derived_result_is_idempotent_and_persists_canonical_artifact(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        artifact = docs_patch.validate_artifact(proposal())
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict("os.environ", {"GC_SERVICE_STATE_ROOT": state_root}), mock.patch.object(
            service, "addressed_sources_by_key", side_effect=[[], [{"id": "ga-result"}]]
        ), mock.patch.object(service, "run_subprocess", return_value=mock.Mock(returncode=0, stdout='{"id":"ga-result"}', stderr="")):
            created = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, artifact)
            duplicate = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, artifact)

            self.assertEqual(created["status"], "created")
            self.assertEqual(duplicate, {**created, "status": "duplicate", "reason": "source_key_exists"})
            self.assertEqual(service.github_pr_docs_patch_key(context, created["patch_sha256"]), created["source_key"])
            self.assertEqual(service.common.read_json(created["artifact_path"])["artifact_sha256"], created["artifact_sha256"])

    def test_regenerated_patch_with_a_new_timestamp_reuses_derived_result_identity(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        first = docs_patch.validate_artifact(proposal())
        regenerated = proposal()
        regenerated["generated_at"] = "2026-08-28T13:00:00Z"
        second = docs_patch.validate_artifact(regenerated)
        self.assertNotEqual(first["artifact_sha256"], second["artifact_sha256"])
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict("os.environ", {"GC_SERVICE_STATE_ROOT": state_root}), mock.patch.object(
            service, "addressed_sources_by_key", side_effect=[[], [{"id": "ga-result"}]]
        ), mock.patch.object(service, "run_subprocess", return_value=mock.Mock(returncode=0, stdout='{"id":"ga-result"}', stderr="")):
            created = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, first)
            duplicate = service.create_pull_request_docs_patch_result(context, {"bead_id": "ga-source"}, second)

        self.assertEqual(created["source_key"], duplicate["source_key"])
        self.assertEqual(created["source_key"], service.github_pr_docs_patch_key(context, first["patch_sha256"]))

    def test_webhook_payload_unwraps_durable_delivery_envelope(self) -> None:
        payload = {"number": 9, "pull_request": {"head": {"sha": "a" * 40}}}
        self.assertEqual(docs_impact.webhook_payload({"event": "pull_request", "payload": payload}), payload)

    def test_evaluate_queues_city_review_without_creating_a_check(self) -> None:
        payload = {
            "repository": {"id": 17, "full_name": "allenday/demo", "name": "demo", "owner": {"login": "allenday"}},
            "pull_request": {"number": 9, "html_url": "https://github.com/allenday/demo/pull/9", "head": {"sha": "a" * 40}},
            "installation": {"id": 44},
        }
        github_requests: list[object] = []
        source_key = "github-pr:17:9:" + "a" * 40
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict("os.environ", {"GC_SERVICE_STATE_ROOT": state_root}), mock.patch.object(
            docs_impact, "create_source", return_value={"status": "created", "bead_id": "ga-1", "source_key": source_key}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=lambda *args: github_requests.append(args)
        ), mock.patch.object(
            service.common, "update_check_run_with_token", side_effect=lambda *args: github_requests.append(args)
        ):
            result = docs_impact.evaluate(payload, "delivery-1", "token", paths=["src/cli.py"])

        self.assertEqual(result["status"], "queued")
        self.assertEqual(github_requests, [])
        self.assertEqual(result["assignment"]["kind"], "github-pr-docs-impact-assignment")
        self.assertEqual(result["assignment"]["identity"]["source_key"], source_key)
        self.assertEqual(result["assignment"]["agent_skill"], "developer-experience-techdocs")

    def test_valid_exact_review_persists_then_creates_one_completed_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40, "bead_id": "mc-private"}
        review = valid_agent_review()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check:
            record = docs_impact.project_agent_review(context, source, review)
            result = docs_impact.publish_agent_review("token", context, review)

        self.assertIsNotNone(record)
        self.assertEqual(result["status"], "published")
        create_check.assert_called_once()
        args = create_check.call_args.args
        self.assertEqual(args[:4], ("token", "allenday", "demo", "a" * 40))
        self.assertEqual(args[5:7], ("completed", "success"))
        self.assertEqual(args[7]["summary"], "The changed behavior is adequately documented.\n\nNext action: No documentation action is required for this revision.")
        self.assertEqual(service.load_docs_impact_run(context)["check_run_id"], "81")

    def test_missing_or_wrong_revision_review_creates_no_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        missing = valid_agent_review()
        missing["identity"].pop("source_key")
        wrong_revision = valid_agent_review("b" * 40)
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(service.common, "create_check_run_with_token") as create_check:
            self.assertIsNone(docs_impact.project_agent_review(context, source, missing))
            self.assertIsNone(docs_impact.project_agent_review(context, source, wrong_revision))
            self.assertEqual(docs_impact.publish_agent_review("token", context, missing)["status"], "ignored")
            self.assertEqual(docs_impact.publish_agent_review("token", context, wrong_revision)["status"], "ignored")

        create_check.assert_not_called()

    def test_review_verdict_selects_the_terminal_check_conclusion(self) -> None:
        expected_conclusions = {
            "no-impact": "success",
            "docs-sufficient": "success",
            "docs-change-required": "action_required",
            "proposal-ready": "action_required",
            "inconclusive": "action_required",
        }
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check:
            for index, (verdict, conclusion) in enumerate(expected_conclusions.items()):
                head_sha = f"{index + 1:x}" * 40
                context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": head_sha}
                source = {"source_key": "github-pr:17:9:" + head_sha}
                review = valid_agent_review(head_sha, verdict)
                self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
                self.assertEqual(docs_impact.publish_agent_review("token", context, review)["status"], "published")
                self.assertEqual(create_check.call_args.args[6], conclusion)

    def test_reprojected_review_does_not_create_a_second_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check:
            docs_impact.project_agent_review(context, source, review)
            docs_impact.publish_agent_review("token", context, review)
            docs_impact.project_agent_review(context, source, review)
            duplicate = docs_impact.publish_agent_review("token", context, review)

        self.assertEqual(duplicate["status"], "duplicate")
        create_check.assert_called_once()

    def test_first_valid_review_is_immutable_against_a_later_valid_review(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        first = valid_agent_review()
        later = valid_agent_review()
        later["rationale"] = "A different valid review must not replace the first decision."
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, first))
            self.assertIsNone(docs_impact.project_agent_review(context, source, later))
            self.assertEqual(docs_impact.publish_agent_review("token", context, later)["status"], "ignored")
            self.assertEqual(docs_impact.publish_agent_review("token", context, first)["status"], "published")

        create_check.assert_called_once()

    def test_retry_after_publication_failure_never_posts_a_second_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=[RuntimeError("connection lost"), {"id": 81}]
        ) as create_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "connection lost"):
                docs_impact.publish_agent_review("token", context, review)
            retry = docs_impact.publish_agent_review("token", context, review)

        self.assertEqual(retry["status"], "publication_pending")
        create_check.assert_called_once()

    def test_check_summary_and_link_hide_the_review_identity(self) -> None:
        head_sha = "a" * 40
        source_key = "github-pr:17:9:" + head_sha
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": head_sha}
        source = {"source_key": source_key}
        review = valid_agent_review()
        review["rationale"] = f"Review {source_key} at {head_sha} for repository 17."
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root, "GITHUB_INTAKE_ADMIN_PUBLIC_URL": "https://city.example"}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            self.assertEqual(docs_impact.publish_agent_review("token", context, review)["status"], "published")

        args = create_check.call_args.args
        self.assertNotIn(source_key, args[7]["summary"])
        self.assertNotIn(head_sha, args[7]["summary"])
        self.assertNotIn("17", args[7]["summary"])
        self.assertNotIn(source_key, args[8])
        self.assertNotIn(head_sha, args[8])
        self.assertNotIn("repository_id", args[8])
        self.assertEqual(args[8], "https://city.example/v0/github/admin/runs?run=" + service.docs_impact_run_locator(context))

    def test_concurrent_publication_creates_one_completed_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []

        def publish() -> None:
            barrier.wait()
            results.append(docs_impact.publish_agent_review("token", context, review))

        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=lambda *args: (time.sleep(0.05) or {"id": 81})
        ) as create_check:
            docs_impact.project_agent_review(context, source, review)
            threads = [threading.Thread(target=publish), threading.Thread(target=publish)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(sorted(result["status"] for result in results), ["duplicate", "published"])
        create_check.assert_called_once()
