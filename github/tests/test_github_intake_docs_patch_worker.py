from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import shlex
import textwrap
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_patch_worker as worker


SHA = "a" * 40


def assignment() -> dict[str, object]:
    return {"schema_version": 1, "kind": "github-pr-docs-impact-assignment", "identity": {"repository_id": "17", "repository": "allenday/demo", "pr_number": 9, "head_sha": SHA, "source_key": f"github-pr:17:9:{SHA}"}, "agent_skill": "developer-experience-techdocs", "evidence_bundle": {"head_sha": SHA, "proposal_identity": {"repository_id": "17", "repository": "allenday/demo", "pr_number": 9, "base_sha": "b" * 40, "head_sha": SHA, "head_repository_id": "17", "head_repository": "allenday/demo", "base_ref": "main"}, "files": [{"path": "docs/guide.md", "reference": f"github://allenday/demo/blob/{SHA}/docs/guide.md", "patch": "@@ -1 +1 @@\n-old\n+new\n"}]}}


class DocsPatchWorkerTests(unittest.TestCase):
    def test_direct_admission_candidate_has_a_separate_v2_validation_boundary(self) -> None:
        self.assertTrue(callable(getattr(worker, "validate_direct_admission_candidate", None)))

    def test_direct_admission_candidate_validates_exact_ordered_classifications(self) -> None:
        from github.tests.test_github_intake_docs_patch import review
        raw = json.dumps(assignment(), sort_keys=True, separators=(",", ":")).encode()
        artifact = review()
        artifact["verdict"] = "docs-change-required"
        artifact["proposal"] = None
        candidate = {
            "schema_version": 2,
            "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            "artifact": artifact,
            "persona_goal_path": {
                "domain": "techdocs", "role": "developer", "job": "use the interface",
                "starting_context": "a checked-out pull request", "success_condition": "the interface is usable",
                "documentation_entry_point": "README.md",
            },
            "coverage_cells": [
                {"identity": "developer:use-interface:how-to", "classification": "unmet", "evidence_paths": ["docs/guide.md"]},
            ],
        }

        validated = worker.validate_direct_admission_candidate(raw, candidate)

        self.assertEqual(validated["schema_version"], 2)
        self.assertEqual(validated["snapshot_sha256"], candidate["snapshot_sha256"])
        self.assertEqual(validated["persona_goal_path"], candidate["persona_goal_path"])
        self.assertEqual(validated["coverage_cells"], candidate["coverage_cells"])
        self.assertEqual(validated["artifact"]["identity"], candidate["artifact"]["identity"])

    def test_direct_admission_rejects_v1_and_malformed_v2_without_changing_legacy_validation(self) -> None:
        from github.tests.test_github_intake_docs_patch import review
        raw = json.dumps(assignment(), sort_keys=True, separators=(",", ":")).encode()
        artifact = review()
        artifact["verdict"] = "docs-change-required"
        artifact["proposal"] = None
        legacy = {"schema_version": 1, "snapshot_sha256": hashlib.sha256(raw).hexdigest(), "artifact": artifact}
        self.assertEqual(worker.validate_final_candidate(raw, legacy)["schema_version"], 1)
        with self.assertRaisesRegex(ValueError, "v2"):
            worker.validate_direct_admission_candidate(raw, legacy)

        base = {
            "schema_version": 2, "snapshot_sha256": hashlib.sha256(raw).hexdigest(), "artifact": artifact,
            "persona_goal_path": {"domain": "techdocs", "role": "developer", "job": "use the interface", "starting_context": "checkout", "success_condition": "usable", "documentation_entry_point": "README.md"},
            "coverage_cells": [{"identity": "developer:use-interface:how-to", "classification": "unmet", "evidence_paths": ["docs/guide.md"]}],
        }
        invalids = [
            {**base, "snapshot_sha256": "0" * 64},
            {**base, "coverage_cells": [{**base["coverage_cells"][0], "classification": "maybe"}]},
            {**base, "coverage_cells": [{**base["coverage_cells"][0], "evidence_paths": ["docs/not-in-assignment.md"]}]},
            {**base, "coverage_cells": [base["coverage_cells"][0], base["coverage_cells"][0]]},
            {**base, "extra": True},
        ]
        for value in invalids:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    worker.validate_direct_admission_candidate(raw, value)

    def test_worker_cli_writes_and_reports_a_normal_final_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            raw = json.dumps(assignment()).encode()
            assignment_file, artifact = root / "assignment.json", root / "artifact.json"
            assignment_file.write_bytes(raw)
            skill = root / "skill"; skill.mkdir(); (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            adapter = root / "adapter.py"
            adapter.write_text(textwrap.dedent("""\
                import json, sys
                assignment = json.load(sys.stdin)
                h = assignment['identity']['head_sha']
                json.dump({'schema_version': 1, 'kind': 'github-pr-docs-impact-review', 'identity': assignment['identity'], 'agent_skill': assignment['agent_skill'], 'verdict': 'docs-sufficient', 'rationale': 'Sufficient.', 'evidence': [{'path': 'docs/guide.md', 'evidence': 'github://' + assignment['identity']['repository'] + '/blob/' + h + '/docs/guide.md'}], 'confidence': 0.9, 'proposal': None}, sys.stdout)
            """), encoding="utf-8")
            result = subprocess.run([sys.executable, str(pathlib.Path(worker.__file__)), "--assignment-file", str(assignment_file), "--artifact-file", str(artifact), "--adapter-command", shlex.join([sys.executable, str(adapter)]), "--skill-dir", str(skill)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            candidate = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(candidate["artifact"]["verdict"], "docs-sufficient")
            self.assertEqual(json.loads(result.stdout)["review_sha256"], candidate["artifact"]["review_sha256"])

    def test_worker_cli_binds_classified_reviewer_output_into_a_v2_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            raw = json.dumps(assignment(), separators=(",", ":")).encode()
            assignment_file, artifact = root / "assignment.json", root / "artifact.json"
            assignment_file.write_bytes(raw)
            skill = root / "skill"; skill.mkdir(); (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            adapter = root / "adapter.py"
            adapter.write_text(textwrap.dedent("""\
                import json, sys
                assignment = json.load(sys.stdin)
                h = assignment['identity']['head_sha']
                review = {'schema_version': 1, 'kind': 'github-pr-docs-impact-review', 'identity': assignment['identity'], 'agent_skill': assignment['agent_skill'], 'verdict': 'docs-change-required', 'rationale': 'The guide is incomplete.', 'evidence': [{'path': 'docs/guide.md', 'evidence': 'github://' + assignment['identity']['repository'] + '/blob/' + h + '/docs/guide.md'}], 'confidence': 0.9, 'proposal': None}
                json.dump({'artifact': review, 'persona_goal_path': {'domain': 'techdocs', 'role': 'developer', 'job': 'use the interface', 'starting_context': 'a checkout', 'success_condition': 'the interface works', 'documentation_entry_point': 'README.md'}, 'coverage_cells': [{'identity': 'developer:use-interface:how-to', 'classification': 'unmet', 'evidence_paths': ['docs/guide.md']}]}, sys.stdout)
            """), encoding="utf-8")
            result = subprocess.run([sys.executable, str(pathlib.Path(worker.__file__)), "--assignment-file", str(assignment_file), "--artifact-file", str(artifact), "--adapter-command", shlex.join([sys.executable, str(adapter)]), "--skill-dir", str(skill)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            candidate = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(candidate["schema_version"], 2)
            self.assertEqual(candidate["snapshot_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(candidate["coverage_cells"][0]["classification"], "unmet")
    def test_final_candidate_accepts_canonical_non_proposal_reviews(self) -> None:
        from github.tests.test_github_intake_docs_patch import review
        raw = json.dumps(assignment()).encode()
        for verdict in ("no-impact", "docs-sufficient", "docs-change-required", "inconclusive"):
            with self.subTest(verdict=verdict):
                value = review()
                value["verdict"] = verdict
                value["proposal"] = None
                self.assertEqual(worker.validate_final_candidate(raw, {"schema_version": 1, "snapshot_sha256": __import__("hashlib").sha256(raw).hexdigest(), "artifact": value})["artifact"]["verdict"], verdict)
    def test_final_candidate_rejects_every_proposal_only_identity_mismatch(self) -> None:
        from github.tests.test_github_intake_docs_patch import review
        raw = json.dumps(assignment()).encode()
        for field, value in (("base_sha", "c" * 40), ("head_repository_id", "18"), ("head_repository", "allenday/other"), ("base_ref", "release")):
            with self.subTest(field=field):
                candidate = review()
                candidate["proposal"]["identity"][field] = value
                with self.assertRaisesRegex(ValueError, "proposal identity"):
                    worker.validate_final_candidate(raw, {"schema_version": 1, "snapshot_sha256": __import__("hashlib").sha256(raw).hexdigest(), "artifact": candidate})

    def test_adapter_environment_strips_caller_and_github_credentials(self) -> None:
        environment = worker._adapter_environment()
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("GH_TOKEN", environment)
        self.assertEqual(set(environment), {"HOME", "PATH", "LANG", "LC_ALL", "PYTHONNOUSERSITE"})

    def test_assignment_bytes_keep_exact_identity_and_skill_binding(self) -> None:
        raw = json.dumps(assignment(), separators=(",", ":")).encode()
        validated = worker.load_assignment_bytes(raw)
        self.assertEqual(validated["identity"], assignment()["identity"])
        self.assertEqual(validated["agent_skill"], "developer-experience-techdocs")

    def test_assignment_rejects_proposal_identity_for_another_revision(self) -> None:
        value = assignment()
        value["evidence_bundle"]["proposal_identity"]["head_sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "proposal identity"):
            worker.validate_assignment(value)

    def test_assignment_rejects_every_mismatched_proposal_identity_field(self) -> None:
        for field, value in (("repository_id", "18"), ("repository", "allenday/other"), ("pr_number", 10), ("head_sha", "c" * 40)):
            with self.subTest(field=field):
                value_to_check = assignment()
                value_to_check["evidence_bundle"]["proposal_identity"][field] = value
                with self.assertRaisesRegex(ValueError, "proposal identity"):
                    worker.validate_assignment(value_to_check)

    def test_assignment_rejects_an_unexpected_reviewer_skill(self) -> None:
        value = assignment()
        value["agent_skill"] = "other-skill"
        with self.assertRaisesRegex(ValueError, "agent_skill"):
            worker.load_assignment_bytes(json.dumps(value).encode())

    def test_credential_error_removes_a_stale_artifact_before_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignment_file = root / "assignment.json"
            artifact_file = root / "artifact.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            artifact_file.write_text('{"stale":true}', encoding="utf-8")
            result = subprocess.run([sys.executable, str(pathlib.Path(worker.__file__)), "--assignment-file", str(assignment_file), "--artifact-file", str(artifact_file)], env={"GITHUB_TOKEN": "present", "PATH": "/usr/bin:/bin"}, text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(artifact_file.exists())


if __name__ == "__main__":
    unittest.main()
