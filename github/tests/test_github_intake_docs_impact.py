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
    def setUp(self) -> None:
        self.remote_head_sha = "a" * 40
        patcher = mock.patch.object(
            service.common,
            "pull_request_head_sha_with_token",
            side_effect=lambda *_args: self.remote_head_sha,
        )
        self.current_head = patcher.start()
        self.addCleanup(patcher.stop)
        update_patcher = mock.patch.object(
            service.common,
            "update_check_run_with_token",
            side_effect=lambda *_args: {"id": _args[3]},
        )
        self.update_check = update_patcher.start()
        self.addCleanup(update_patcher.stop)

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
        self.assertEqual(args[5:7], ("in_progress", None))
        self.assertEqual(args[7]["summary"], "The changed behavior is adequately documented.\n\nNext action: No documentation action is required for this revision.")
        self.update_check.assert_called_once_with(
            "token",
            "allenday",
            "demo",
            81,
            "completed",
            "success",
            args[7],
        )
        self.assertEqual(service.load_docs_impact_run(context)["check_run_id"], "81")

    def test_head_change_during_check_creation_neutralizes_stale_success(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()

        def create_check(*_args: object, **_kwargs: object) -> dict[str, object]:
            self.remote_head_sha = "b" * 40
            return {"id": 81}

        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=create_check
        ), mock.patch.object(
            service.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "action_required"}
        ) as update_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            result = docs_impact.publish_agent_review("token", context, review)
            record = service.load_docs_impact_run(context)

        self.assertEqual(
            result,
            {"status": "ignored", "reason": "head_sha_changed", "head_sha": "a" * 40, "check_run_id": "81"},
        )
        self.assertEqual(record["publication_state"], "stale")
        self.assertEqual(record["check_run_id"], "81")
        update_check.assert_called_once_with(
            "token",
            "allenday",
            "demo",
            81,
            "completed",
            "action_required",
            {
                "title": "Documentation impact: stale revision",
                "summary": "This check was invalidated because the pull request revision could not be confirmed as current.",
            },
        )

    def test_post_create_head_lookup_failure_neutralizes_then_fails_closed(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ), mock.patch.object(
            service.common, "pull_request_head_sha_with_token", side_effect=RuntimeError("head unavailable")
        ), mock.patch.object(
            service.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "action_required"}
        ) as update_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "head unavailable"):
                docs_impact.publish_agent_review("token", context, review)
            record = service.load_docs_impact_run(context)

        update_check.assert_called_once()
        self.assertEqual(record["publication_state"], "stale")
        self.assertEqual(record["check_run_id"], "81")

    def test_neutralization_failure_records_retryable_neutralization_intent(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        self.remote_head_sha = "b" * 40
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ), mock.patch.object(
            service.common, "update_check_run_with_token", side_effect=RuntimeError("neutralization failed")
        ):
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "neutralization failed"):
                docs_impact.publish_agent_review("token", context, review)
            record = service.load_docs_impact_run(context)

        self.assertEqual(record["publication_state"], "neutralizing")
        self.assertEqual(record["check_run_id"], "81")

    def test_stale_state_write_failure_retries_only_neutralization(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        self.remote_head_sha = "b" * 40
        real_atomic_write = service.common.atomic_write_json
        stale_write_failed = False

        def fail_first_stale_write(path: str, value: dict[str, object], mode: int = 0o640) -> None:
            nonlocal stale_write_failed
            if value.get("publication_state") == "stale" and not stale_write_failed:
                stale_write_failed = True
                raise RuntimeError("stale state write failed")
            real_atomic_write(path, value, mode)

        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check, mock.patch.object(
            service.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "action_required"}
        ) as update_check, mock.patch.object(
            service.common, "atomic_write_json", side_effect=fail_first_stale_write
        ):
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "stale state write failed"):
                docs_impact.publish_agent_review("token", context, review)
            self.assertEqual(service.load_docs_impact_run(context)["publication_state"], "neutralizing")

            retry = docs_impact.publish_agent_review("token", context, review)
            record = service.load_docs_impact_run(context)

        self.assertEqual(retry, {"status": "ignored", "reason": "publication_stale", "check_run_id": "81"})
        self.assertEqual(record["publication_state"], "stale")
        create_check.assert_called_once()
        self.assertEqual(update_check.call_count, 2)

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
                self.remote_head_sha = head_sha
                context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": head_sha}
                source = {"source_key": "github-pr:17:9:" + head_sha}
                review = valid_agent_review(head_sha, verdict)
                self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
                self.assertEqual(docs_impact.publish_agent_review("token", context, review)["status"], "published")
                self.assertEqual(self.update_check.call_args.args[5], conclusion)

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

    def test_retry_after_pre_acceptance_failure_creates_one_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=[RuntimeError("connection lost"), {"id": 81}]
        ) as create_check, mock.patch.object(
            service.common, "find_check_run_by_external_id_with_token", return_value=None
        ) as find_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "connection lost"):
                docs_impact.publish_agent_review("token", context, review)
            retry = docs_impact.publish_agent_review("token", context, review)

        self.assertEqual(retry["status"], "published")
        self.assertEqual(create_check.call_count, 2)
        self.assertEqual(
            create_check.call_args.kwargs["external_id"],
            service.docs_impact_check_external_id(service.docs_impact_run_locator(context)),
        )
        find_check.assert_called_once()

    def test_retry_after_ambiguous_acceptance_adopts_the_remote_check(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        external_id = service.docs_impact_check_external_id(service.docs_impact_run_locator(context))
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=RuntimeError("response lost")
        ) as create_check, mock.patch.object(
            service.common, "find_check_run_by_external_id_with_token",
            return_value={"id": 81, "external_id": external_id},
        ) as find_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                docs_impact.publish_agent_review("token", context, review)
            retry = docs_impact.publish_agent_review("token", context, review)

        self.assertEqual(retry["status"], "adopted")
        create_check.assert_called_once()
        find_check.assert_called_once_with("token", "allenday", "demo", "a" * 40, external_id)
        self.assertEqual(service.load_docs_impact_run(context)["check_run_id"], "81")

    def test_retry_adoption_neutralizes_a_check_for_a_superseded_head(self) -> None:
        context = {"repository_id": "17", "repository": "allenday/demo", "number": "9", "head_sha": "a" * 40}
        source = {"source_key": "github-pr:17:9:" + "a" * 40}
        review = valid_agent_review()
        external_id = service.docs_impact_check_external_id(service.docs_impact_run_locator(context))
        with tempfile.TemporaryDirectory() as state_root, mock.patch.dict(
            "os.environ", {"GC_SERVICE_STATE_ROOT": state_root}
        ), mock.patch.object(
            service.common, "create_check_run_with_token", side_effect=RuntimeError("response lost")
        ), mock.patch.object(
            service.common, "find_check_run_by_external_id_with_token",
            return_value={"id": 81, "external_id": external_id},
        ), mock.patch.object(
            service.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "action_required"}
        ) as update_check:
            self.assertIsNotNone(docs_impact.project_agent_review(context, source, review))
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                docs_impact.publish_agent_review("token", context, review)
            self.remote_head_sha = "b" * 40
            retry = docs_impact.publish_agent_review("token", context, review)

        self.assertEqual(retry["status"], "ignored")
        self.assertEqual(retry["reason"], "head_sha_changed")
        update_check.assert_called_once()

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
            service.common, "create_check_run_with_token", side_effect=lambda *args, **kwargs: (time.sleep(0.05) or {"id": 81})
        ) as create_check, mock.patch.object(
            service.common, "find_check_run_by_external_id_with_token", return_value=None
        ):
            docs_impact.project_agent_review(context, source, review)
            threads = [threading.Thread(target=publish), threading.Thread(target=publish)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(sorted(result["status"] for result in results), ["duplicate", "published"])
        create_check.assert_called_once()
