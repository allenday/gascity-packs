from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_city_docs_launcher as launcher
from github.tests.test_github_intake_docs_patch_worker import assignment


class CityDocsLauncherTests(unittest.TestCase):
    def test_dispatches_validated_immutable_assignment_via_gc_sling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, immutable, candidates, state = (
                root / "snapshots",
                root / "immutable",
                root / "candidates",
                root / "state",
            )
            snapshots.mkdir()
            snapshot = snapshots / "revision-bound.json"
            snapshot.write_text(json.dumps(assignment()), encoding="utf-8")
            commands: list[list[str]] = []

            def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if "create" in command:
                    return subprocess.CompletedProcess(command, 0, '{"id":"gc-review-1"}\n', "")
                return subprocess.CompletedProcess(command, 0, '{"status":"routed"}\n', "")

            self.assertEqual(
                launcher.dispatch_once(
                    snapshots,
                    immutable,
                    candidates,
                    state,
                    city_path="/city",
                    target="github.docs-impact-reviewer",
                    run=run,
                ),
                1,
            )

            digest = launcher.snapshot_sha256(snapshot.read_bytes())
            self.assertEqual((immutable / f"{digest}.json").read_bytes(), snapshot.read_bytes())
            self.assertEqual(commands[0][:5], ["gc", "--city", "/city", "bd", "create"])
            metadata = json.loads(commands[0][commands[0].index("--metadata") + 1])
            self.assertEqual(metadata["github.docs_review.snapshot_sha256"], digest)
            self.assertEqual(
                commands[1],
                [
                    "gc", "--city", "/city", "sling", "github.docs-impact-reviewer",
                    "gc-review-1", "--no-convoy", "--no-formula", "--nudge", "--json",
                ],
            )
            marker = json.loads((state / f"{digest}.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["bead_id"], "gc-review-1")
            self.assertEqual(marker["snapshot_name"], snapshot.name)

    def test_current_digest_bound_candidate_prevents_duplicate_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots, immutable, candidates, state = (
                root / "snapshots", root / "immutable", root / "candidates", root / "state",
            )
            snapshots.mkdir()
            candidates.mkdir()
            snapshot = snapshots / "revision-bound.json"
            raw = json.dumps(assignment()).encode("utf-8")
            snapshot.write_bytes(raw)
            candidate = {
                "schema_version": 1,
                "snapshot_sha256": launcher.snapshot_sha256(raw),
                "artifact": {
                    "schema_version": 1,
                    "kind": "github-pr-docs-impact-review",
                    "identity": assignment()["identity"],
                    "agent_skill": "developer-experience-techdocs",
                    "verdict": "docs-sufficient",
                    "rationale": "The behavior and its developer-facing use are documented.",
                    "evidence": [{
                        "path": "docs/guide.md",
                        "evidence": assignment()["evidence_bundle"]["files"][0]["reference"],
                    }],
                    "confidence": 0.9,
                    "proposal": None,
                },
            }
            (candidates / snapshot.name).write_text(json.dumps(candidate), encoding="utf-8")

            def unexpected(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                self.fail("gc must not run for a current candidate")

            self.assertEqual(
                launcher.dispatch_once(
                    snapshots,
                    immutable,
                    candidates,
                    state,
                    city_path="/city",
                    target="github.docs-impact-reviewer",
                    run=unexpected,
                ),
                0,
            )

    def test_rejects_malformed_assignment_before_creating_a_bead(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshots = root / "snapshots"
            snapshots.mkdir()
            (snapshots / "bad.json").write_text('{"repository":"owner/repo"}', encoding="utf-8")

            def unexpected(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                self.fail("gc must not run for malformed evidence")

            self.assertEqual(
                launcher.dispatch_once(
                    snapshots,
                    root / "immutable",
                    root / "candidates",
                    root / "state",
                    city_path="/city",
                    target="github.docs-impact-reviewer",
                    run=unexpected,
                ),
                0,
            )
