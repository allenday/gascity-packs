from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_intake_docs_journey_commands import _strict_json_object, record_update, start_or_admit


SHA = "a" * 40


def request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository_id": "17",
        "repository": "allenday/demo",
        "installation_id": "91",
        "default_branch": "main",
        "default_branch_sha": SHA,
        "source": {
            "kind": "github-issue",
            "key": "github-issue:17:42",
            "url": "https://github.com/allenday/demo/issues/42",
            "issue_number": 42,
            "projection_capabilities": ["issue-comment"],
        },
        "domain": "techdocs",
        "role": "developer",
        "job": "install the package",
        "starting_context": "a clone of the repository",
        "success_condition": "the package is installed successfully",
        "backfill_policy": "blocking-only",
        "docs_impact_source_key": "github-pr:17:9:" + SHA,
        "budgets": {
            "max_depth": 2,
            "max_children": 1,
            "max_docs_prs": 1,
            "max_debt_issues": 1,
            "max_elapsed_seconds": 3600,
            "max_non_progress": 3,
        },
    }
    value.update(overrides)
    return value


def decision() -> dict[str, object]:
    return {
        "artifact": {
            "schema_version": 1,
            "kind": "github-pr-docs-impact-review",
            "identity": {
                "repository_id": "17",
                "repository": "allenday/demo",
                "pr_number": 9,
                "head_sha": SHA,
                "source_key": "github-pr:17:9:" + SHA,
            },
            "agent_skill": "developer-experience-techdocs",
            "verdict": "docs-change-required",
            "rationale": "The install guide needs one bounded correction.",
            "evidence": [{"path": "docs/install.md", "evidence": f"github://allenday/demo/blob/{SHA}/docs/install.md"}],
            "confidence": 0.9,
            "proposal": None,
        },
        "journey_disposition": "blocking",
    }


class DocsJourneyCommandTests(unittest.TestCase):
    def test_start_or_admit_persists_and_adopts_exact_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = {"request": request(), "decision": decision()}
            first = start_or_admit(directory, payload, now=100)
            journey = first["journey"]
            self.assertEqual(first["action"]["kind"], "create_issue")
            self.assertTrue((pathlib.Path(directory) / "journeys").is_dir())

            replay = start_or_admit(directory, payload, now=101)
            self.assertEqual(replay["journey"], journey)
            self.assertIsNone(replay["action"])

    def test_start_or_admit_rejects_same_identity_with_changed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            start_or_admit(directory, {"request": request(), "decision": decision()}, now=100)
            changed = request(role="operator")
            with self.assertRaisesRegex(ValueError, "does not match"):
                start_or_admit(directory, {"request": changed, "decision": decision()}, now=101)

    def test_record_child_update_persists_only_admitted_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = start_or_admit(directory, {"request": request(), "decision": decision()}, now=100)
            journey = started["journey"]
            child = journey["children"][0]
            result = record_update(directory, {
                "identity": journey["identity"],
                "update": {
                    "schema_version": 1,
                    "kind": "github-docs-journey-child-update",
                    "admitted_child": child,
                    "state": "complete",
                    "documentation_branch": {
                        "branch": "gas-city/docs-install",
                        "commit_sha": SHA,
                        "evidence": ["commit:abcdef"],
                    },
                },
            })
            self.assertEqual(result["action"]["kind"], "create_docs_pr")
            self.assertNotIn("Document installation", result["action"]["body"])
            self.assertIn("Admitted evidence surfaces", result["action"]["body"])
            self.assertEqual(result["action"]["worker_evidence"], ["commit:abcdef"])
            self.assertEqual(result["action"]["commit_sha"], SHA)
            self.assertEqual(result["journey"]["children"][0]["state"], "complete")
            self.assertEqual(result["journey"]["docs_prs_used"], 1)

    def test_commands_reject_unknown_fields_and_duplicate_json_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            _strict_json_object('{"request": {}, "request": {}}')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unexpected extra"):
                start_or_admit(directory, {"request": request(), "decision": decision(), "extra": True}, now=100)

    def test_v2_worker_cannot_supply_public_pull_request_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = start_or_admit(directory, {"request": request(), "decision": decision()}, now=100)
            journey = started["journey"]
            updated = record_update(directory, {
                "identity": journey["identity"],
                "update": {
                    "schema_version": 1,
                    "kind": "github-docs-journey-child-update",
                    "admitted_child": journey["children"][0],
                    "state": "complete",
                    "documentation_pr": {"branch": "gas-city/forbidden", "title": "Worker title"},
                },
            })
            self.assertIsNone(updated["action"])
            self.assertEqual(updated["journey"]["children"][0]["state"], "admitted")
