from __future__ import annotations

import json
import hashlib
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_patch_queue_worker as queue_worker
from github.tests.test_github_intake_docs_patch_worker import proposal


class DocsPatchQueueWorkerTests(unittest.TestCase):
    def test_consumes_one_sanitized_snapshot_into_matching_artifact_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, artifacts = root / "snapshots", root / "artifacts"
            snapshots.mkdir()
            (snapshots / "revision-bound.json").write_text(
                json.dumps({"schema_version": 1, "proposal": proposal()}), encoding="utf-8",
            )

            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 1)

            envelope = json.loads((artifacts / "revision-bound.json").read_text(encoding="utf-8"))
            self.assertEqual(envelope["artifact"]["identity"]["head_sha"], "a" * 40)
            self.assertEqual(envelope["snapshot_sha256"], queue_worker.snapshot_sha256(snapshots / "revision-bound.json"))
            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 0)

    def test_recomputes_artifact_when_snapshot_changes_for_same_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, artifacts = root / "snapshots", root / "artifacts"
            snapshots.mkdir()
            snapshot = snapshots / "revision-bound.json"
            snapshot.write_text(json.dumps({"schema_version": 1, "proposal": proposal()}), encoding="utf-8")
            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 1)
            first = json.loads((artifacts / snapshot.name).read_text(encoding="utf-8"))["snapshot_sha256"]

            revised = proposal()
            revised["claims"][0]["claim"] = "Revised docs claim."
            snapshot.write_text(json.dumps({"schema_version": 1, "proposal": revised}), encoding="utf-8")

            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 1)
            second = json.loads((artifacts / snapshot.name).read_text(encoding="utf-8"))
            self.assertNotEqual(second["snapshot_sha256"], first)
            self.assertEqual(second["snapshot_sha256"], queue_worker.snapshot_sha256(snapshot))

    def test_recomputes_malformed_artifact_after_sidecar_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, artifacts = root / "snapshots", root / "artifacts"
            snapshots.mkdir()
            snapshot = snapshots / "revision-bound.json"
            snapshot.write_text(json.dumps({"schema_version": 1, "proposal": proposal()}), encoding="utf-8")
            artifacts.mkdir()
            (artifacts / snapshot.name).write_text("{not-json", encoding="utf-8")

            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 1)
            recovered = json.loads((artifacts / snapshot.name).read_text(encoding="utf-8"))
            self.assertEqual(recovered["snapshot_sha256"], queue_worker.snapshot_sha256(snapshot))

    def test_snapshot_replacement_after_read_cannot_mix_digest_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, artifacts = root / "snapshots", root / "artifacts"
            snapshots.mkdir()
            snapshot = snapshots / "revision-bound.json"
            original = json.dumps({"schema_version": 1, "proposal": proposal()}).encode("utf-8")
            snapshot.write_bytes(original)
            captured_bytes = snapshot.read_bytes()
            replacement = proposal()
            replacement["claims"][0]["claim"] = "Replacement that must not leak into this result."
            snapshot.write_text(json.dumps({"schema_version": 1, "proposal": replacement}), encoding="utf-8")

            self.assertTrue(queue_worker.consume_snapshot(snapshot, captured_bytes, artifacts / snapshot.name))

            envelope = json.loads((artifacts / snapshot.name).read_text(encoding="utf-8"))
            self.assertEqual(envelope["snapshot_sha256"], hashlib.sha256(original).hexdigest())
            self.assertNotIn("Replacement that must not leak", json.dumps(envelope))
