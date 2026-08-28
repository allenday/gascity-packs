from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_impact_pipeline as pipeline


class DocsImpactPipelineTests(unittest.TestCase):
    def test_sidecar_output_requires_the_exact_snapshot_digest_and_protocol_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = pathlib.Path(temp_dir) / "snapshot.json"
            snapshot.write_text('{"schema_version":1}', encoding="utf-8")
            artifact = {"from": "sidecar"}
            current = {"schema_version": 1, "snapshot_sha256": pipeline.snapshot_sha256(snapshot), "artifact": artifact}

            self.assertEqual(pipeline.unwrap_current_artifact(snapshot, current), artifact)
            self.assertIsNone(pipeline.unwrap_current_artifact(snapshot, {**current, "snapshot_sha256": "0" * 64}))
            self.assertIsNone(pipeline.unwrap_current_artifact(snapshot, {**current, "schema_version": 2}))

    def test_handoff_enqueues_sanitized_snapshot_and_consumes_sidecar_artifact(self) -> None:
        payload = {
            "repository": {"id": 17, "full_name": "allenday/demo", "name": "demo", "owner": {"login": "allenday"}},
            "number": 9,
            "pull_request": {"head": {"sha": "a" * 40}, "base": {"sha": "b" * 40, "ref": "main"}},
        }
        proposal = {"schema_version": 1, "proposal": {"safe": "input"}}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            proposal_file = root / "proposal.json"
            proposal_file.write_text(json.dumps(proposal), encoding="utf-8")
            captured: dict[str, object] = {}

            def wait_for_artifact(snapshot_file: pathlib.Path, artifact_file: pathlib.Path) -> dict[str, object] | None:
                captured["snapshot"] = json.loads(snapshot_file.read_text(encoding="utf-8"))
                artifact_file.write_text(json.dumps({"artifact": "from-worker"}), encoding="utf-8")
                return json.loads(artifact_file.read_text(encoding="utf-8"))

            with mock.patch.object(pipeline.common, "list_pull_request_files_with_token", return_value=[{"filename": "src/widget.py"}]), mock.patch.object(
                pipeline.docs_impact, "evaluate", return_value={"outcome": "proposed"}
            ) as evaluate:
                result = pipeline.run_handoff(
                    payload, "delivery-1", "secret", proposal_file, root / "snapshots", root / "artifacts", wait_for_artifact,
                )

        self.assertEqual(result["outcome"], "proposed")
        self.assertEqual(captured["snapshot"]["changed_paths"], ["src/widget.py"])
        self.assertEqual(captured["snapshot"]["proposal"], proposal["proposal"])
        self.assertEqual(evaluate.call_args.args[3], {"artifact": "from-worker"})
        self.assertNotIn("secret", json.dumps(captured["snapshot"]))

    def test_handoff_without_proposal_evaluates_human_friendly_fallback(self) -> None:
        payload = {
            "repository": {"id": 17, "full_name": "allenday/demo", "name": "demo", "owner": {"login": "allenday"}},
            "number": 9,
            "pull_request": {"head": {"sha": "a" * 40}, "base": {"sha": "b" * 40, "ref": "main"}},
        }
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            pipeline.common, "list_pull_request_files_with_token", return_value=[{"filename": "github/scripts/intake.py"}]
        ), mock.patch.object(pipeline.docs_impact, "evaluate", return_value={"outcome": "needs-human-decision"}) as evaluate:
            result = pipeline.run_handoff(
                payload, "delivery-1", "secret", None, pathlib.Path(temp_dir) / "snapshots", pathlib.Path(temp_dir) / "artifacts", mock.Mock(),
            )

        self.assertEqual(result["outcome"], "needs-human-decision")
        self.assertEqual(evaluate.call_args.args[3], None)
        self.assertEqual(evaluate.call_args.kwargs["paths"], ["github/scripts/intake.py"])
