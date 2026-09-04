from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_intake_docs_journey_commands import _strict_json_object, activate_bud, project_until_settled, record_update, start_or_admit


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
    def test_activate_bud_creates_a_fresh_v3_record_only_for_its_recorded_identity(self) -> None:
        v3_request = {
            "repository_id": "17", "repository": "allenday/demo", "installation_id": "91",
            "context": {"kind": "github-issue", "key": "github-issue:17:42", "url": "https://example.test/issues/42",
                        "docs_impact_source_key": "github-pr:17:9:" + SHA, "default_branch": "main", "default_branch_sha": SHA},
            "persona_goal_paths": [{"domain": "techdocs", "role": "developer", "job": "install",
                                    "starting_context": "clone", "success_condition": "installed", "documentation_entry_point": "README.md"}],
            "budgets": {"max_depth": 1, "max_children": 1, "max_docs_prs": 1, "max_buds": 1,
                        "max_elapsed_seconds": 60, "max_non_progress": 1},
        }
        with tempfile.TemporaryDirectory() as directory:
            started = start_or_admit(directory, {"request": v3_request, "decision": {**decision(), "journey_disposition": "non-blocking"}}, now=100)
            old = started["journey"]
            bud = old["buds"][0]
            replay = start_or_admit(directory, {"request": v3_request, "decision": {**decision(), "journey_disposition": "non-blocking"}}, now=101)
            self.assertEqual(replay["journey"], old)
            activated = activate_bud(directory, {
                "identity": old["identity"], "bud_identity": bud["identity"],
                "context": {**old["context"], "key": "operator-request:17:99", "kind": "operator-request", "url": "https://example.test/requests/99"},
            }, now=101)
            self.assertNotEqual(activated["journey"]["identity"], old["identity"])
            self.assertEqual(activated["journey"]["context"]["kind"], "operator-request")
            self.assertEqual(old["buds"][0]["state"], "recorded")

    def test_activate_bud_requires_the_recorded_identity_and_a_new_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            budded = start_or_admit(directory, {"request": request(backfill_policy="record-debt"), "decision": {**decision(), "journey_disposition": "non-blocking"}}, now=100)
            old = budded["journey"]
            with self.assertRaisesRegex(ValueError, "bud was not found"):
                activate_bud(directory, {"identity": old["identity"], "bud_identity": "wrong", "context": {}})
            with self.assertRaisesRegex(ValueError, "new context"):
                activate_bud(directory, {"identity": old["identity"], "bud_identity": old["debts"][0]["key"], "context": old["source"]})
    def test_project_until_settled_rejects_nonconvergent_pending_actions_at_its_bound(self) -> None:
        pending = {"state": "active", "actions": [{"id": "pending", "state": "pending"}], "children": []}
        with mock.patch("github_intake_docs_journey_commands.project_configured_journey", return_value=pending) as project:
            with self.assertRaisesRegex(RuntimeError, "did not settle within 2 passes"):
                project_until_settled("/state", "journey", max_passes=2)

        self.assertEqual(project.call_count, 2)

    def test_project_until_settled_waits_for_issue_bead_and_assignment_before_worker_readiness(self) -> None:
        class Adapter:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def _resource(self, action: dict[str, object]) -> dict[str, str]:
                self.calls.append(str(action["kind"]))
                return {"id": str(action["kind"]), "logical_id": str(action["id"])}

            def create_issue(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
                return self._resource(action)

            def create_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
                return self._resource(action)

            def assign_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
                return self._resource(action)

            def create_debt_issue(self, root: dict[str, object], action: dict[str, object], debt: dict[str, object]) -> dict[str, str]:
                return self._resource(action)

            def create_docs_pr(self, root: dict[str, object], action: dict[str, object], child: dict[str, object] | None) -> dict[str, str]:
                return self._resource(action)

            def post_root_status(self, root: dict[str, object], action: dict[str, object]) -> dict[str, str]:
                return self._resource(action)

        with tempfile.TemporaryDirectory() as directory:
            started = start_or_admit(directory, {"request": request(), "decision": decision()}, now=100)
            adapter = Adapter()
            with mock.patch("github_docs_journey.common.load_effective_config", return_value={"app": {"slug": "gas-city"}}), mock.patch(
                "github_docs_journey.GitHubCityBootstrapAdapter", return_value=adapter,
            ), mock.patch("github_docs_journey.time.time", return_value=101):
                result = project_until_settled(directory, started["journey"]["identity"])

            self.assertTrue(result["settled"])
            self.assertEqual(result["passes"], 3)
            self.assertEqual(adapter.calls, ["create_issue", "create_bead", "assign_bead"])
            self.assertEqual(result["worker_ready_children"], [started["journey"]["children"][0]["key"]])

            update = {
                "schema_version": 1,
                "kind": "github-docs-journey-child-update",
                "admitted_child": result["journey"]["children"][0],
                "state": "complete",
                "documentation_branch": {
                    "branch": "gas-city/docs-install",
                    "commit_sha": SHA,
                    "evidence": ["commit:abcdef"],
                },
            }
            record_update(directory, {"identity": result["journey"]["identity"], "update": update})
            with mock.patch("github_docs_journey.common.load_effective_config", return_value={"app": {"slug": "gas-city"}}), mock.patch(
                "github_docs_journey.GitHubCityBootstrapAdapter", return_value=adapter,
            ), mock.patch("github_docs_journey.time.time", return_value=101):
                completed = project_until_settled(directory, result["journey"]["identity"])

            self.assertTrue(completed["settled"])
            self.assertEqual(completed["journey"]["state"], "baseline-complete")
            self.assertEqual(adapter.calls, ["create_issue", "create_bead", "assign_bead", "create_docs_pr", "post_root_status"])

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
