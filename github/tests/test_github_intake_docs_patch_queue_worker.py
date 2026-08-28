from __future__ import annotations

import json
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

            artifact = json.loads((artifacts / "revision-bound.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["identity"]["head_sha"], "a" * 40)
            self.assertEqual(queue_worker.consume_once(snapshots, artifacts), 0)
