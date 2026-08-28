from __future__ import annotations

import hashlib
import json
import pathlib
import shlex
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_patch_queue_worker as queue_worker
from github.tests.test_github_intake_docs_patch_worker import assignment, review, write_adapter, write_skill


class DocsPatchQueueWorkerTests(unittest.TestCase):
    def test_consumes_one_assignment_into_matching_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            adapter, skill = write_adapter(root), write_skill(root)

            self.assertEqual(
                queue_worker.consume_once(
                    assignments,
                    artifacts,
                    adapter_command=shlex.join([sys.executable, str(adapter)]),
                    skill_dir=skill,
                ),
                1,
            )

            envelope = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))
            self.assertEqual(envelope["artifact"]["kind"], "github-pr-docs-impact-review")
            self.assertEqual(envelope["artifact"]["identity"], assignment()["identity"])
            self.assertEqual(envelope["snapshot_sha256"], queue_worker.snapshot_sha256(assignment_file))
            self.assertEqual(
                queue_worker.consume_once(
                    assignments,
                    artifacts,
                    adapter_command=shlex.join([sys.executable, str(adapter)]),
                    skill_dir=skill,
                ),
                0,
            )

    def test_unconfigured_adapter_produces_no_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")

            self.assertEqual(
                queue_worker.consume_once(assignments, artifacts, adapter_command="", skill_dir=write_skill(root)),
                0,
            )
            self.assertFalse((artifacts / assignment_file.name).exists())

    def test_matching_digest_wrong_revision_candidate_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            artifacts.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            candidate_file = artifacts / assignment_file.name
            candidate_file.write_text(queue_worker.docs_patch.canonical_json({
                "schema_version": 1,
                "snapshot_sha256": queue_worker.snapshot_sha256(assignment_file),
                "artifact": queue_worker.docs_patch.validate_agent_review(review("b" * 40)),
            }) + "\n", encoding="utf-8")

            self.assertEqual(
                queue_worker.consume_once(assignments, artifacts, adapter_command="", skill_dir=write_skill(root)),
                0,
            )

            self.assertFalse(candidate_file.exists())

    def test_recomputes_candidate_when_assignment_changes_for_same_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            adapter, skill = write_adapter(root), write_skill(root)
            command = shlex.join([sys.executable, str(adapter)])
            self.assertEqual(queue_worker.consume_once(
                assignments, artifacts, adapter_command=command, skill_dir=skill,
            ), 1)
            first = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))

            assignment_file.write_text(
                json.dumps(assignment(changed_paths=["docs/guide.md", "src/cli.py"])),
                encoding="utf-8",
            )

            self.assertEqual(queue_worker.consume_once(
                assignments, artifacts, adapter_command=command, skill_dir=skill,
            ), 1)
            second = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))
            self.assertNotEqual(second["snapshot_sha256"], first["snapshot_sha256"])
            self.assertEqual(second["snapshot_sha256"], queue_worker.snapshot_sha256(assignment_file))

    def test_recomputes_malformed_candidate_after_worker_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            artifacts.mkdir()
            (artifacts / assignment_file.name).write_text("{not-json", encoding="utf-8")
            adapter, skill = write_adapter(root), write_skill(root)

            self.assertEqual(queue_worker.consume_once(
                assignments,
                artifacts,
                adapter_command=shlex.join([sys.executable, str(adapter)]),
                skill_dir=skill,
            ), 1)

            recovered = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))
            self.assertEqual(recovered["snapshot_sha256"], queue_worker.snapshot_sha256(assignment_file))

    def test_snapshot_replacement_after_read_cannot_mix_digest_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            original = json.dumps(assignment()).encode("utf-8")
            assignment_file.write_bytes(original)
            captured_bytes = assignment_file.read_bytes()
            assignment_file.write_text(json.dumps(assignment("b" * 40)), encoding="utf-8")
            adapter, skill = write_adapter(root), write_skill(root)

            self.assertTrue(queue_worker.consume_snapshot(
                assignment_file,
                captured_bytes,
                artifacts / assignment_file.name,
                adapter_command=shlex.join([sys.executable, str(adapter)]),
                skill_dir=skill,
            ))

            envelope = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))
            self.assertEqual(envelope["snapshot_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(envelope["artifact"]["identity"]["head_sha"], "a" * 40)

    def test_adapter_verdict_is_preserved_instead_of_derived_from_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignments, artifacts = root / "assignments", root / "artifacts"
            assignments.mkdir()
            assignment_file = assignments / "revision-bound.json"
            assignment_file.write_text(
                json.dumps(assignment(changed_paths=["docs/guide.md", "src/cli.py"])),
                encoding="utf-8",
            )
            adapter, skill = write_adapter(root), write_skill(root)

            self.assertEqual(queue_worker.consume_once(
                assignments,
                artifacts,
                adapter_command=shlex.join([sys.executable, str(adapter), "--verdict", "docs-change-required"]),
                skill_dir=skill,
            ), 1)

            envelope = json.loads((artifacts / assignment_file.name).read_text(encoding="utf-8"))
            self.assertEqual(envelope["artifact"]["verdict"], "docs-change-required")
