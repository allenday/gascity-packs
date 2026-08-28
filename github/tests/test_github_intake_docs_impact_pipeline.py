from __future__ import annotations

import hashlib
import json
import pathlib
import shlex
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_impact_pipeline as pipeline
import github_intake_docs_patch_queue_worker as queue_worker
from github.tests.test_github_intake_docs_patch_worker import (
    assignment,
    review,
    write_adapter,
    write_skill,
)


def payload(head_sha: str = "a" * 40) -> dict[str, object]:
    return {
        "repository": {
            "id": 17,
            "full_name": "allenday/demo",
            "name": "demo",
            "owner": {"login": "allenday"},
        },
        "number": 9,
        "pull_request": {
            "number": 9,
            "html_url": "https://github.com/allenday/demo/pull/9",
            "head": {"sha": head_sha},
            "base": {"sha": "b" * 40, "ref": "main"},
        },
        "installation": {"id": 44},
    }


def envelope(raw: bytes, candidate: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact": candidate,
    }


class DocsImpactPipelineTests(unittest.TestCase):
    def test_exact_sha_evidence_resists_mutable_pr_files_a_to_b_to_a_race(self) -> None:
        context = pipeline.service.github_pr_context(payload())
        exact_patch = "@@ -1 +1 @@\n-old-a\n+new-a"
        poisoned_patch = "@@ -1 +1 @@\n-old-b\n+new-b"

        with mock.patch.object(
            pipeline.common,
            "pull_request_head_sha_with_token",
            side_effect=["a" * 40, "a" * 40],
        ), mock.patch.object(
            pipeline.common,
            "list_pull_request_files_with_token",
            return_value=[{"filename": "docs/guide.md", "patch": poisoned_patch}],
        ) as mutable_files, mock.patch.object(
            pipeline.common,
            "compare_commits_with_token",
            return_value=[{"filename": "docs/guide.md", "patch": exact_patch}],
        ) as exact_files:
            bundle = pipeline.evidence_bundle("token", context)

        self.assertEqual(bundle["files"][0]["patch"], exact_patch)
        exact_files.assert_called_once_with(
            "token", "allenday", "demo", "b" * 40, "a" * 40,
        )
        mutable_files.assert_not_called()

    def test_head_change_after_queue_before_projection_creates_no_check(self) -> None:
        current_head = ["a" * 40]

        def remote_head(*_args: object) -> str:
            return current_head[0]

        def completed_review(
            _assignment_file: pathlib.Path, _artifact_file: pathlib.Path, _wait_seconds: float,
        ) -> dict[str, object]:
            current_head[0] = "b" * 40
            return review()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            queued = {
                "status": "queued",
                "source": {"source_key": assignment()["identity"]["source_key"]},
                "assignment": assignment(),
                "assignment_path": str(assignments / "revision.json"),
                "head_sha": "a" * 40,
            }
            with mock.patch.object(
                pipeline.common, "pull_request_head_sha_with_token", side_effect=remote_head
            ), mock.patch.object(
                pipeline.common,
                "list_pull_request_files_with_token",
                return_value=[{"filename": "docs/guide.md", "patch": "@@ -1 +1 @@\n-old\n+new"}],
            ), mock.patch.object(
                pipeline.common,
                "compare_commits_with_token",
                return_value=[{"filename": "docs/guide.md", "patch": "@@ -1 +1 @@\n-old\n+new"}],
            ), mock.patch.object(
                pipeline.docs_impact, "evaluate", return_value=queued
            ) as evaluate, mock.patch.object(
                pipeline.docs_impact, "project_agent_review"
            ) as project, mock.patch.object(
                pipeline.docs_impact, "publish_agent_review"
            ) as publish:
                result = pipeline.run_handoff(
                    payload(),
                    "delivery-1",
                    "token",
                    assignments,
                    artifacts,
                    completed_review,
                    wait_seconds=0,
                )

        self.assertEqual(
            result,
            {"status": "ignored", "reason": "head_sha_changed", "head_sha": "a" * 40},
        )
        evaluate.assert_called_once()
        project.assert_not_called()
        publish.assert_not_called()

    def test_head_change_before_queue_fails_before_source_or_queue_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            pipeline.common,
            "pull_request_head_sha_with_token",
            return_value="b" * 40,
        ), mock.patch.object(
            pipeline.common,
            "compare_commits_with_token",
            return_value=[{"filename": "docs/guide.md", "patch": "@@ -1 +1 @@\n-old\n+new"}],
        ), mock.patch.object(pipeline.docs_impact, "evaluate") as evaluate:
            root = pathlib.Path(temp_dir)
            result = pipeline.run_handoff(
                payload(), "delivery-1", "token", root / "assignments", root / "artifacts", wait_seconds=0
            )

        self.assertEqual(result, {"status": "ignored", "reason": "head_sha_changed", "head_sha": "a" * 40})
        evaluate.assert_not_called()

    def test_oversized_patch_or_total_evidence_fails_before_queueing(self) -> None:
        cases = {
            "single_patch": [{
                "filename": "docs/large.md",
                "patch": "x" * (pipeline.MAX_EVIDENCE_PATCH_BYTES + 1),
            }],
            "aggregate": [{
                "filename": f"docs/{index}.md",
                "patch": "x" * (pipeline.MAX_EVIDENCE_PATCH_BYTES - 1024),
            } for index in range(5)],
        }
        for name, files in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
                pipeline.common,
                "pull_request_head_sha_with_token",
                return_value="a" * 40,
            ), mock.patch.object(
                pipeline.common, "compare_commits_with_token", return_value=files
            ), mock.patch.object(pipeline.docs_impact, "evaluate") as evaluate:
                root = pathlib.Path(temp_dir)
                result = pipeline.run_handoff(
                    payload(), "delivery-1", "token", root / "assignments", root / "artifacts", wait_seconds=0
                )

            self.assertEqual(result["status"], "ignored")
            self.assertEqual(result["reason"], "evidence_unsafe")
            evaluate.assert_not_called()

    def test_candidate_requires_exact_assignment_digest_identity_and_skill(self) -> None:
        raw = json.dumps(assignment()).encode("utf-8")
        valid = envelope(raw, review())
        canonical = pipeline.validate_review_candidate(raw, valid)

        self.assertIsNotNone(canonical)
        self.assertEqual(canonical["identity"], assignment()["identity"])
        self.assertEqual(canonical["agent_skill"], assignment()["agent_skill"])
        invalid = [
            {**valid, "schema_version": True},
            {**valid, "snapshot_sha256": "0" * 64},
            envelope(raw, review("b" * 40)),
            {**valid, "artifact": {**review(), "agent_skill": "another-skill"}},
            {"schema_version": 1, "snapshot_sha256": valid["snapshot_sha256"]},
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                self.assertIsNone(pipeline.validate_review_candidate(raw, candidate))

    def test_malformed_stale_or_mismatched_candidate_never_reaches_projector(self) -> None:
        raw = json.dumps(assignment()).encode("utf-8")
        invalid = [
            {"not": "an envelope"},
            envelope(raw, review("b" * 40)),
            {**envelope(raw, review()), "snapshot_sha256": "0" * 64},
        ]
        for index, candidate in enumerate(invalid):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp_dir:
                root = pathlib.Path(temp_dir)
                assignments, artifacts = root / "assignments", root / "artifacts"
                assignments.mkdir()
                artifacts.mkdir()
                assignment_file = assignments / "revision.json"
                assignment_file.write_bytes(raw)
                artifact_file = artifacts / assignment_file.name
                artifact_file.write_text(json.dumps(candidate), encoding="utf-8")
                queued = {
                    "status": "queued",
                    "source": {"source_key": assignment()["identity"]["source_key"]},
                    "assignment": assignment(),
                    "assignment_path": str(assignment_file),
                    "head_sha": "a" * 40,
                }
                with mock.patch.object(
                    pipeline.common, "pull_request_head_sha_with_token", return_value="a" * 40
                ), mock.patch.object(
                    pipeline.common, "compare_commits_with_token", return_value=[]
                ), mock.patch.object(
                    pipeline.docs_impact, "evaluate", return_value=queued
                ), mock.patch.object(
                    pipeline.docs_impact, "project_agent_review"
                ) as project, mock.patch.object(
                    pipeline.docs_impact, "publish_agent_review"
                ) as publish:
                    result = pipeline.run_handoff(
                        payload(),
                        "delivery-1",
                        "token",
                        assignments,
                        artifacts,
                        pipeline.wait_for_sidecar_review,
                        wait_seconds=0,
                    )

                self.assertEqual(result["status"], "queued")
                project.assert_not_called()
                publish.assert_not_called()

    def test_assignment_to_adapter_candidate_to_trusted_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            adapter, skill = write_adapter(root), write_skill(root)
            source_key = assignment()["identity"]["source_key"]
            source = {"status": "created", "bead_id": "mc-private", "source_key": source_key}
            with mock.patch.dict("os.environ", {
                "GC_SERVICE_STATE_ROOT": str(root / "state"),
                "GC_GITHUB_DOCS_PATCH_SNAPSHOT_DIR": str(assignments),
            }), mock.patch.object(
                pipeline.common, "pull_request_head_sha_with_token", return_value="a" * 40
            ), mock.patch.object(
                pipeline.common,
                "compare_commits_with_token",
                return_value=[{"filename": "docs/guide.md", "patch": "@@ -1 +1 @@\n-old\n+new"}],
            ), mock.patch.object(
                pipeline.docs_impact, "create_source", return_value=source
            ), mock.patch.object(
                pipeline.service.common, "create_check_run_with_token", return_value={"id": 81}
            ) as create_check:

                def complete_adapter_work(
                    assignment_file: pathlib.Path, artifact_file: pathlib.Path, wait_seconds: float,
                ) -> dict[str, object] | None:
                    self.assertTrue(assignment_file.exists())
                    self.assertFalse(artifact_file.exists())
                    create_check.assert_not_called()
                    self.assertEqual(queue_worker.consume_once(
                        assignments,
                        artifacts,
                        adapter_command=shlex.join([sys.executable, str(adapter)]),
                        skill_dir=skill,
                    ), 1)
                    return pipeline.wait_for_sidecar_review(assignment_file, artifact_file, wait_seconds)

                result = pipeline.run_handoff(
                    payload(),
                    "delivery-1",
                    "token",
                    assignments,
                    artifacts,
                    complete_adapter_work,
                    wait_seconds=0,
                )

            self.assertEqual(result["status"], "published")
            create_check.assert_called_once()
            self.assertEqual(create_check.call_args.args[5:7], ("completed", "success"))
            record = pipeline.service.load_docs_impact_run({
                "repository_id": "17",
                "repository": "allenday/demo",
                "number": "9",
                "head_sha": "a" * 40,
            })
            self.assertEqual(record["check_run_id"], "81")
            self.assertNotIn("mc-private", pipeline.service.render_docs_impact_run(record))
