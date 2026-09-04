from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_intake_docs_journey_commands import _strict_json_object, activate_bud, project_until_settled, record_update, start_or_admit
import github_intake_docs_direct_child_complete as direct_child


SHA = "a" * 40


def direct_patch_artifact() -> dict[str, object]:
    """One bounded documentation-only patch against the admitted PR snapshot."""
    diff = "diff --git a/docs/install.md b/docs/install.md\nindex 1111111..2222222 100644\n--- a/docs/install.md\n+++ b/docs/install.md\n@@ -1 +1 @@\n-old\n+new\n"
    return {
        "schema_version": 1,
        "status": "proposed",
        "generated_at": "2026-09-04T12:00:00Z",
        "identity": {
            "repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
            "base_sha": "b" * 40, "head_sha": SHA,
            "head_repository_id": "17", "head_repository": "allenday/demo", "base_ref": "main",
        },
        "patch_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "diff": diff,
        "files": [{"path": "docs/install.md", "sha256": "c" * 64}],
        "claims": [{"claim": "The install guide explains the new workflow.",
                    "evidence": f"github://allenday/demo/blob/{SHA}/docs/install.md",
                    "release_scope": "unreleased"}],
        "checks": [{"command": "make docs-check", "status": "passed", "explanation": "Documentation checks passed."}],
    }


def direct_assignment() -> dict[str, object]:
    return {
        "schema_version": 1, "kind": "github-pr-docs-impact-assignment",
        "identity": {"repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
                     "head_sha": SHA, "source_key": "github-pr:17:9:" + SHA},
        "agent_skill": "developer-experience-techdocs",
        "evidence_bundle": {
            "head_sha": SHA,
            "proposal_identity": {"repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
                                  "base_sha": "b" * 40, "head_sha": SHA, "head_repository_id": "17",
                                  "head_repository": "allenday/demo", "base_ref": "main"},
            "files": [{"path": "docs/install.md", "reference": f"github://allenday/demo/blob/{SHA}/docs/install.md",
                       "patch": "@@ -1 +1 @@\n-old\n+new\n"}],
        },
    }


def direct_candidate(raw: bytes | None = None) -> dict[str, object]:
    raw = raw or json.dumps(direct_assignment(), sort_keys=True, separators=(",", ":")).encode()
    artifact = decision()["artifact"]
    return {
        "schema_version": 2, "snapshot_sha256": hashlib.sha256(raw).hexdigest(), "artifact": artifact,
        "persona_goal_path": {"domain": "techdocs", "role": "developer", "job": "install",
                              "starting_context": "clone", "success_condition": "installed",
                              "documentation_entry_point": "README.md"},
        "coverage_cells": [{"identity": "developer:install:how-to", "classification": "unmet",
                            "evidence_paths": ["docs/install.md"]}],
    }


def direct_context(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
        "source_key": "github-pr:17:9:" + SHA, "reviewed_head_sha": SHA,
        "source_branch": "feature/install", "source_url": "https://github.com/allenday/demo/pull/9",
        "installation_id": "91",
    }
    value.update(overrides)
    return value


def direct_payload(**overrides: object) -> dict[str, object]:
    raw = json.dumps(direct_assignment(), sort_keys=True, separators=(",", ":")).encode()
    value: dict[str, object] = {
        "assignment_bytes": base64.b64encode(raw).decode("ascii"),
        "candidate": direct_candidate(raw), "context": direct_context(),
    }
    value.update(overrides)
    return value


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
    def test_pack_exposes_a_direct_admission_boundary(self) -> None:
        self.assertTrue(callable(getattr(direct_child, "admit_direct_child", None)))

    def test_direct_admission_persists_and_returns_full_pack_issued_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admitted = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            replay = direct_child.admit_direct_child(directory, direct_payload(), now=101)

        self.assertEqual(replay, admitted)
        self.assertEqual(set(admitted), {"schema_version", "kind", "recursion_identity", "admitted_child", "patch_context"})
        self.assertEqual(admitted["patch_context"]["proposal_identity"], direct_assignment()["evidence_bundle"]["proposal_identity"])
        self.assertTrue(admitted["recursion_identity"].startswith("github-docs-recursion:17:github-pr:17:9:"))
        child = admitted["admitted_child"]
        for field in ("key", "identity", "state", "depth", "snapshot_sha", "decision_identity",
                      "decision_digest", "evidence_paths", "context", "persona_goal_path"):
            self.assertIn(field, child)
        self.assertEqual(child["context"]["pr_number"], 9)
        self.assertEqual(child["context"]["source_branch"], "feature/install")
        self.assertEqual(child["context"]["default_branch"], "feature/install")

    def test_direct_admission_has_no_projectable_city_work_for_the_dispatched_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admitted = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            stored = direct_child.FileJourneyStore(directory).load(admitted["recursion_identity"])

        self.assertFalse(any(
            action.get("child_key") == admitted["admitted_child"]["key"]
            and action.get("kind") in {"create_issue", "create_bead", "assign_bead"}
            for action in stored["actions"]
        ))

    def test_direct_admission_cli_returns_the_persisted_pack_record(self) -> None:
        script = pathlib.Path(direct_child.__file__).with_name("github_intake_docs_direct_child_admit.py")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script), "--once", "--store", directory, "--input", json.dumps(direct_payload())],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        admitted = json.loads(result.stdout)
        self.assertEqual(admitted["kind"], "github-docs-recursion-direct-admission")
        self.assertEqual(admitted["admitted_child"]["context"]["source_branch"], "feature/install")

    def test_direct_admission_cross_checks_every_context_duplicate_and_is_transactional(self) -> None:
        mismatches = {
            "repository_id": "18", "repository": "allenday/other", "pr_number": 10,
            "source_key": "github-pr:17:10:" + SHA, "reviewed_head_sha": "c" * 40,
            "source_url": "https://github.com/allenday/demo/pull/10",
        }
        for field, changed in mismatches.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                payload = direct_payload(context=direct_context(**{field: changed}))
                with self.assertRaisesRegex(ValueError, "context"):
                    direct_child.admit_direct_child(directory, payload, now=100)
                self.assertEqual(list((pathlib.Path(directory) / "journeys").glob("*.json")), [])

    def test_direct_admission_rejects_changed_replay_without_overwriting_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admitted = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            changed = direct_candidate()
            changed["persona_goal_path"] = {**changed["persona_goal_path"], "job": "install safely"}
            with self.assertRaisesRegex(ValueError, "persisted direct admission"):
                direct_child.admit_direct_child(directory, direct_payload(candidate=changed), now=101)
            stored = direct_child.FileJourneyStore(directory).load(admitted["recursion_identity"])
        self.assertEqual(stored["children"][0], admitted["admitted_child"])

    def test_direct_completion_consumes_exact_admission_and_replays_idempotently(self) -> None:
        class Publisher:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def publish(self, admission: dict[str, object], review: dict[str, object], **kwargs: object) -> dict[str, object]:
                self.calls.append({"admission": admission, "review": review})
                return {"branch": "gas-city/docs-9-0123456789ab", "commit_sha": SHA,
                        "evidence": ["commit:" + SHA]}

        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            update = {
                "schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                "admitted_child": admission["admitted_child"], "state": "complete",
                "patch_context": admission["patch_context"],
                "documentation_patch": direct_patch_artifact(),
            }
            publisher = Publisher()
            first = direct_child.complete_direct_child(directory, {"admission": admission, "update": update}, publisher=publisher)
            replay = direct_child.complete_direct_child(directory, {"admission": admission, "update": update}, publisher=publisher)

        self.assertEqual(replay, first)
        self.assertEqual(len(publisher.calls), 1)
        self.assertEqual(publisher.calls[0]["review"]["proposal"]["patch_sha256"], update["documentation_patch"]["patch_sha256"])
        self.assertEqual(first["action"]["kind"], "create_docs_pr")
        self.assertEqual(first["action"]["base"], "feature/install")

    def test_direct_completion_rejects_a_worker_branch_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            update = {
                "schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                "admitted_child": admission["admitted_child"], "state": "complete",
                "patch_context": admission["patch_context"],
                "documentation_branch": {"branch": "gas-city/direct-child", "commit_sha": SHA,
                                         "evidence": ["commit:" + SHA]},
            }
            with self.assertRaisesRegex(ValueError, "documentation_patch"):
                direct_child.complete_direct_child(directory, {"admission": admission, "update": update})

    def test_direct_completion_rejects_a_patch_for_another_immutable_snapshot_before_publish(self) -> None:
        class Publisher:
            def publish(self, admission: dict[str, object], review: dict[str, object]) -> dict[str, object]:
                self.fail("publisher must not receive an inapplicable patch")

        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            patch = direct_patch_artifact()
            patch["identity"] = {**patch["identity"], "head_sha": "c" * 40}
            update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                      "admitted_child": admission["admitted_child"], "state": "complete",
                      "patch_context": admission["patch_context"],
                      "documentation_patch": patch}
            with self.assertRaisesRegex(ValueError, "immutable snapshot"):
                direct_child.complete_direct_child(directory, {"admission": admission, "update": update}, publisher=Publisher())
            stored = direct_child.FileJourneyStore(directory).load(admission["recursion_identity"])

        self.assertEqual(stored["children"][0]["state"], "admitted")

    def test_direct_completion_requires_the_exact_pack_issued_patch_context_echo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                      "admitted_child": admission["admitted_child"], "state": "blocked",
                      "patch_context": {**admission["patch_context"], "proposal_identity": {}},
                      "documentation_patch": None}
            with self.assertRaisesRegex(ValueError, "patch context"):
                direct_child.complete_direct_child(directory, {"admission": admission, "update": update})

    def test_trusted_direct_publisher_refuses_to_adopt_a_preexisting_branch(self) -> None:
        class Gateway:
            def pull_request(self, run: dict[str, object]) -> dict[str, object]:
                return {
                    "number": 9,
                    "head": {"sha": SHA, "ref": "feature/install", "repo": {"id": 17, "full_name": "allenday/demo"}},
                    "base": {"sha": "b" * 40, "ref": "main", "repo": {"id": 17, "full_name": "allenday/demo"}},
                }

            def branch_exists(self, repository: str, branch: str) -> bool:
                return True

        publisher = direct_child.GitHubDirectPatchPublisher({}, "91")
        publisher.gateway = Gateway()
        review = {**decision()["artifact"], "verdict": "proposal-ready", "proposal": direct_patch_artifact()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            publisher.publish({}, review)

    def test_trusted_direct_publisher_adopts_only_its_exact_durable_pre_push_intent(self) -> None:
        class Gateway:
            def pull_request(self, run: dict[str, object]) -> dict[str, object]:
                return {
                    "number": 9,
                    "head": {"sha": SHA, "ref": "feature/install", "repo": {"id": 17, "full_name": "allenday/demo"}},
                    "base": {"sha": "b" * 40, "ref": "main", "repo": {"id": 17, "full_name": "allenday/demo"}},
                }

            def branch_exists(self, repository: str, branch: str) -> bool:
                return True

            def branch_matches(self, repository: str, branch: str, marker: str, commit_sha: str = "") -> bool:
                return commit_sha == SHA

        publisher = direct_child.GitHubDirectPatchPublisher({}, "91")
        publisher.gateway = Gateway()
        review = {**decision()["artifact"], "verdict": "proposal-ready", "proposal": direct_patch_artifact()}
        proposal = direct_child.docs_patch.validate_artifact(direct_patch_artifact())
        intent = {"repository": "allenday/demo", "branch": "gas-city/docs-9-" + proposal["patch_sha256"][:12],
                  "marker": "gas-city-docs-followup:" + proposal["artifact_sha256"], "commit_sha": SHA}
        published = publisher.publish({}, review, published_intent=intent)

        self.assertEqual(published["commit_sha"], SHA)

    def test_trusted_direct_publisher_rechecks_the_source_head_after_push(self) -> None:
        class Gateway:
            def __init__(self) -> None:
                self.pulls = 0

            def pull_request(self, run: dict[str, object]) -> dict[str, object]:
                self.pulls += 1
                head_sha = SHA if self.pulls == 1 else "c" * 40
                return {
                    "number": 9,
                    "head": {"sha": head_sha, "ref": "feature/install", "repo": {"id": 17, "full_name": "allenday/demo"}},
                    "base": {"sha": "b" * 40, "ref": "main", "repo": {"id": 17, "full_name": "allenday/demo"}},
                }

            def branch_exists(self, repository: str, branch: str) -> bool:
                return False

            def create_branch(self, repository: str, branch: str, head_sha: str, review: dict[str, object], marker: str, before_push: object) -> str:
                return SHA

            def branch_matches(self, repository: str, branch: str, marker: str, commit_sha: str = "") -> bool:
                return True

        publisher = direct_child.GitHubDirectPatchPublisher({}, "91")
        publisher.gateway = Gateway()
        review = {**decision()["artifact"], "verdict": "proposal-ready", "proposal": direct_patch_artifact()}
        with self.assertRaisesRegex(ValueError, "changed before publication completed"):
            publisher.publish({}, review)

    def test_direct_completion_rejects_partial_or_changed_child_and_bare_gas_city_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            for admitted_child, branch in (({"identity": admission["admitted_child"]["identity"]}, "gas-city/child"),
                                           (admission["admitted_child"], "gas-city/")):
                with self.subTest(admitted_child=admitted_child, branch=branch):
                    update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                              "admitted_child": admitted_child, "state": "complete",
                              "patch_context": admission["patch_context"],
                              "documentation_branch": {"branch": branch, "commit_sha": SHA, "evidence": ["commit:" + SHA]}}
                    with self.assertRaises(ValueError):
                        direct_child.complete_direct_child(directory, {"admission": admission, "update": update})

    def test_direct_completion_accepts_a_terminal_result_without_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
            update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                      "admitted_child": admission["admitted_child"], "state": "blocked",
                      "patch_context": admission["patch_context"], "documentation_patch": None}
            result = direct_child.complete_direct_child(directory, {"admission": admission, "update": update})

        self.assertIsNone(result["action"])
        self.assertEqual(result["journey"]["children"][0]["state"], "blocked")

    def test_direct_completion_enforces_terminal_state_branch_pairs_before_persistence(self) -> None:
        invalid_pairs = [("complete", None)] + [
            (state, {"branch": "gas-city/direct-child", "commit_sha": SHA, "evidence": ["commit:" + SHA]})
            for state in ("blocked", "failed", "cancelled")
        ]
        for state, branch in invalid_pairs:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
                update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                          "admitted_child": admission["admitted_child"], "state": state,
                          "patch_context": admission["patch_context"],
                          "documentation_patch": branch}
                with self.assertRaisesRegex(ValueError, "state.*documentation_patch|documentation_patch.*state"):
                    direct_child.complete_direct_child(directory, {"admission": admission, "update": update})
                stored = direct_child.FileJourneyStore(directory).load(admission["recursion_identity"])
                self.assertEqual(stored["children"][0]["state"], "admitted")

    def test_direct_completion_rejects_the_superseded_identity_update_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            v3_request = {
                "repository_id": "17", "repository": "allenday/demo", "installation_id": "91",
                "context": {"kind": "github-pr", "key": "github-pr:17:9:" + SHA,
                            "url": "https://github.com/allenday/demo/pull/9",
                            "docs_impact_source_key": "github-pr:17:9:" + SHA,
                            "default_branch": "main", "default_branch_sha": SHA},
                "persona_goal_path": {"domain": "techdocs", "role": "developer", "job": "install",
                                      "starting_context": "clone", "success_condition": "installed",
                                      "documentation_entry_point": "README.md"},
                "coverage_cells": ["install"],
                "execution_budgets": {"max_depth": 1, "max_children": 1, "max_docs_prs": 1,
                                      "max_elapsed_seconds": 60, "max_non_progress": 1},
            }
            v3_decision = {**decision(), "coverage_cells": [{"identity": "install", "classification": "unmet", "evidence_paths": ["docs/install.md"]}]}
            started = start_or_admit(directory, {"request": v3_request, "decision": v3_decision}, now=100)
            journey = started["journey"]
            child = journey["children"][0]
            update = {
                "schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                "admitted_child": child, "state": "complete",
                "patch_context": {},
                "documentation_patch": direct_patch_artifact(),
            }
            with self.assertRaisesRegex(ValueError, "Pack-issued admission"):
                direct_child.complete_direct_child(directory, {"identity": journey["identity"], "update": update})

    def test_direct_completion_rejects_an_invented_admission_for_a_legacy_journey(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = start_or_admit(directory, {"request": request(), "decision": decision()}, now=100)
            journey, child = started["journey"], started["journey"]["children"][0]
            admission = {"schema_version": 1, "kind": "github-docs-recursion-direct-admission",
                         "recursion_identity": journey["identity"], "admitted_child": child, "patch_context": {}}
            update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                      "admitted_child": child, "state": "blocked", "patch_context": {}, "documentation_patch": None}
            with self.assertRaisesRegex(ValueError, "direct admission was not found"):
                direct_child.complete_direct_child(directory, {"admission": admission, "update": update})

    def test_direct_completion_rejects_invalid_branch_sha_and_evidence_without_persisting(self) -> None:
        invalid_branches = [
            {"branch": "gas-city/child..lock", "commit_sha": SHA, "evidence": ["commit:" + SHA]},
            {"branch": "gas-city/child", "commit_sha": "short", "evidence": ["commit:" + SHA]},
            {"branch": "gas-city/child", "commit_sha": SHA, "evidence": []},
        ]
        for branch in invalid_branches:
            with self.subTest(branch=branch), tempfile.TemporaryDirectory() as directory:
                admission = direct_child.admit_direct_child(directory, direct_payload(), now=100)
                update = {"schema_version": 1, "kind": "github-docs-recursion-direct-child-update",
                          "admitted_child": admission["admitted_child"], "state": "complete",
                          "patch_context": admission["patch_context"],
                          "documentation_branch": branch}
                with self.assertRaises(ValueError):
                    direct_child.complete_direct_child(directory, {"admission": admission, "update": update})
                stored = direct_child.FileJourneyStore(directory).load(admission["recursion_identity"])
                self.assertEqual(stored["children"][0], admission["admitted_child"])
    def test_activate_bud_creates_a_fresh_v3_record_only_for_its_recorded_identity(self) -> None:
        v3_request = {
            "repository_id": "17", "repository": "allenday/demo", "installation_id": "91",
            "context": {"kind": "github-issue", "key": "github-issue:17:42", "url": "https://example.test/issues/42",
                        "docs_impact_source_key": "github-pr:17:9:" + SHA, "default_branch": "main", "default_branch_sha": SHA},
            "persona_goal_paths": [{"domain": "techdocs", "role": "developer", "job": "install",
                                    "starting_context": "clone", "success_condition": "installed", "documentation_entry_point": "README.md"}],
            "coverage_cells": ["default", "deferred"],
            "budgets": {"max_depth": 1, "max_children": 1, "max_docs_prs": 1, "max_buds": 1,
                        "max_elapsed_seconds": 60, "max_non_progress": 1},
        }
        with tempfile.TemporaryDirectory() as directory:
            assessment = {**decision(), "coverage_cells": [{"identity": "default", "classification": "unmet", "evidence_paths": ["docs/install.md"]}, {"identity": "deferred", "classification": "unmet", "evidence_paths": ["docs/extra.md"]}]}
            started = start_or_admit(directory, {"request": v3_request, "decision": assessment}, now=100)
            old = started["journey"]
            bud = old["buds"][0]
            replay = start_or_admit(directory, {"request": v3_request, "decision": assessment}, now=101)
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
