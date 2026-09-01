from __future__ import annotations

import hashlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_docs_bootstrap import admit_child, new_root, project_actions, reconcile_root


SHA = "a" * 40


def request(**overrides: object) -> dict[str, object]:
    root: dict[str, object] = {
        "explicit": True,
        "repository_id": "17",
        "repository": "allenday/demo",
        "installation_id": "91",
        "root_issue_number": 42,
        "root_issue_url": "https://github.com/allenday/demo/issues/42",
        "default_branch": "main",
        "default_branch_sha": SHA,
    }
    root.update(overrides)
    return root


def decision(**overrides: object) -> dict[str, object]:
    product_ambiguity = overrides.pop("product_ambiguity", False)
    depth = overrides.pop("depth", None)
    result: dict[str, object] = {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-review",
        "identity": {
            "repository_id": "17",
            "repository": "allenday/demo",
            "pr_number": 42,
            "head_sha": SHA,
            "source_key": "github-pr:17:42:" + SHA,
        },
        "agent_skill": "developer-experience-techdocs",
        "verdict": "docs-change-required",
        "rationale": "A bounded documentation change is required.",
        "evidence": [
            {"path": "docs/guide.md", "evidence": f"github://allenday/demo/blob/{SHA}/docs/guide.md"},
            {"path": "README.md", "evidence": f"github://allenday/demo/blob/{SHA}/README.md"},
        ],
        "confidence": 0.9,
        "proposal": None,
    }
    result.update(overrides)
    metadata: dict[str, object] = {"artifact": result}
    if product_ambiguity:
        metadata["product_ambiguity"] = True
    if depth is not None:
        metadata["depth"] = depth
    return metadata if len(metadata) > 1 else result


class RecordingAdapter:
    """In-memory external systems which reconcile by durable action ID."""

    def __init__(self, fail_after: set[str] | None = None) -> None:
        self.fail_after = fail_after or set()
        self.created: dict[str, list[str]] = {"issue": [], "bead": [], "assignment": [], "status": [], "pr": []}
        self.resources: dict[str, dict[str, str]] = {}

    def _adopt(self, kind: str, action: dict[str, object]) -> dict[str, str]:
        action_id = str(action["id"])
        resource = self.resources.setdefault(action_id, {"id": kind + "-" + str(len(self.resources) + 1), "logical_id": action_id})
        if action_id not in self.created[kind]:
            self.created[kind].append(action_id)
        if kind in self.fail_after:
            raise RuntimeError("crash after external " + kind + " creation")
        return resource

    def create_issue(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._adopt("issue", action)

    def create_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._adopt("bead", action)

    def assign_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._adopt("assignment", action)

    def post_root_status(self, root: dict[str, object], action: dict[str, object]) -> dict[str, str]:
        return self._adopt("status", action)

    def create_docs_pr(self, root: dict[str, object], action: dict[str, object], child: dict[str, object] | None) -> dict[str, str]:
        return self._adopt("pr", action)


class DocsBootstrapTests(unittest.TestCase):
    def test_projection_replays_a_persisted_issue_intent_without_duplicate_resources(self) -> None:
        root, _ = admit_child(new_root(request(), now=100), decision(), now=101)
        adapter = RecordingAdapter()

        # The durable root is reloaded after a crash before its first projection.
        self.assertEqual(adapter.created["issue"], [])
        resumed = project_actions(root, adapter)
        replayed = project_actions(resumed, adapter)
        replayed = project_actions(replayed, adapter)

        child = replayed["children"][0]
        self.assertEqual(adapter.created["issue"], ["bootstrap-child:" + child["key"] + ":create_issue"])
        self.assertEqual(adapter.created["bead"], ["bootstrap-child:" + child["key"] + ":create_bead"])
        self.assertEqual(adapter.created["assignment"], ["bootstrap-child:" + child["key"] + ":assign_bead"])
        self.assertEqual([action["state"] for action in replayed["actions"]], ["completed"] * 3)

    def test_projection_recovers_partial_issue_and_bead_projection_after_restart(self) -> None:
        root, _ = admit_child(new_root(request(), now=100), decision(), now=101)
        adapter = RecordingAdapter()
        after_issue = project_actions(root, adapter)
        adapter.fail_after.add("bead")

        with self.assertRaises(RuntimeError):
            project_actions(after_issue, adapter)
        self.assertEqual(after_issue["actions"][1]["state"], "pending")
        self.assertEqual(adapter.created["issue"], [after_issue["actions"][0]["id"]])
        self.assertEqual(adapter.created["bead"], ["bootstrap-child:" + after_issue["children"][0]["key"] + ":create_bead"])

        adapter.fail_after.clear()
        restarted = project_actions(after_issue, adapter)
        restarted = project_actions(restarted, adapter)

        child = restarted["children"][0]
        self.assertEqual(adapter.created["issue"], ["bootstrap-child:" + child["key"] + ":create_issue"])
        self.assertEqual(adapter.created["bead"], ["bootstrap-child:" + child["key"] + ":create_bead"])
        self.assertEqual(adapter.created["assignment"], ["bootstrap-child:" + child["key"] + ":assign_bead"])

    def test_projection_adopts_existing_terminal_resources_by_action_id(self) -> None:
        root = new_root(request(), now=100)
        root["state"] = "cancelled"
        root["actions"] = [{
            "id": "bootstrap-root:" + root["identity"] + ":status:cancelled",
            "kind": "post_root_status", "state": "pending", "state_name": "cancelled",
        }]
        adapter = RecordingAdapter()

        projected = project_actions(root, adapter)
        replayed = project_actions(projected, adapter)

        self.assertEqual(adapter.created["status"], [projected["actions"][0]["id"]])
        self.assertEqual(replayed["actions"][0]["state"], "completed")

    def test_projection_completes_a_persisted_docs_pr_intent_once(self) -> None:
        root = new_root(request(), now=100)
        root["children"] = [{"key": "x"}]
        root["actions"] = [{"id": "bootstrap-child:x:create_docs_pr", "kind": "create_docs_pr", "state": "pending", "child_key": "x"}]
        adapter = RecordingAdapter()

        projected = project_actions(root, adapter)
        project_actions(projected, adapter)

        self.assertEqual(adapter.created["pr"], ["bootstrap-child:x:create_docs_pr"])
        self.assertEqual(projected["actions"][0]["state"], "completed")
    def test_new_root_uses_exact_immutable_identity_and_defaults(self) -> None:
        root = new_root(request(), now=100)

        self.assertEqual(root["identity"], f"github-docs-bootstrap:17:42:{SHA}")
        self.assertEqual(root["state"], "active")
        self.assertEqual(root["budgets"], {
            "max_depth": 2, "max_children": 8, "max_docs_prs": 4,
            "max_elapsed_seconds": 24 * 60 * 60, "max_non_progress": 3,
        })
        self.assertEqual(root["children"], [])
        self.assertEqual(root["visited_surfaces"], [])
        self.assertEqual(root["created_at"], 100)

    def test_new_root_rejects_non_explicit_and_invalid_identity_inputs(self) -> None:
        with self.assertRaises(ValueError):
            new_root(request(explicit=False), now=100)
        with self.assertRaises(ValueError):
            new_root(request(default_branch_sha="not-a-sha"), now=100)

    def test_admission_binds_exact_decision_and_normalized_evidence_paths(self) -> None:
        root = new_root(request(), now=100)
        admitted, action = admit_child(root, decision(evidence=[
            {"path": "README.md", "evidence": f"github://allenday/demo/blob/{SHA}/README.md"},
            {"path": "docs//guide.md", "evidence": f"github://allenday/demo/blob/{SHA}/docs/guide.md"},
            {"path": "README.md", "evidence": f"github://allenday/demo/blob/{SHA}/README.md"},
        ]), now=101)

        self.assertEqual(action["id"], f"bootstrap-child:{admitted['children'][0]['key']}:create_issue")
        self.assertEqual(admitted["children"][0]["evidence_paths"], ["README.md", "docs/guide.md"])
        self.assertEqual(admitted["children"][0]["bootstrap_identity"], root["identity"])
        self.assertEqual(admitted["children"][0]["snapshot_sha"], SHA)
        self.assertEqual(admitted["visited_surfaces"], ["README.md", "docs/guide.md"])

    def test_duplicate_decision_adopts_existing_child(self) -> None:
        root, first = admit_child(new_root(request(), now=100), decision(), now=101)
        replayed, second = admit_child(root, decision(), now=102)

        self.assertEqual(replayed, root)
        self.assertIsNone(second)
        self.assertIsNotNone(first)

    def test_visited_surface_suppresses_a_distinct_decision(self) -> None:
        root, _ = admit_child(new_root(request(), now=100), decision(), now=101)
        replayed, action = admit_child(root, decision(identity={
            "repository_id": "17", "repository": "allenday/demo",
            "pr_number": 43, "head_sha": SHA, "source_key": "github-pr:17:43:" + SHA,
        }, evidence=[{"path": "README.md", "evidence": f"github://allenday/demo/blob/{SHA}/README.md"}]), now=102)

        self.assertEqual(replayed, root)
        self.assertIsNone(action)

    def test_stale_snapshot_terminalizes_for_owner_review(self) -> None:
        root = new_root(request(), now=100)
        updated, action = admit_child(root, decision(identity={
            "repository_id": "17", "repository": "allenday/demo",
            "pr_number": 42, "head_sha": "b" * 40, "source_key": "github-pr:17:42:" + "b" * 40,
        }), now=101)

        self.assertEqual(updated["state"], "owner-review-required")
        self.assertEqual(action["kind"], "post_root_status")

    def test_each_budget_boundary_terminalizes_before_admission(self) -> None:
        for budget, child, candidate in (
            ("max_depth", {}, decision(depth=3)),
            ("max_children", {"children_used": 8}, decision()),
            ("max_docs_prs", {"docs_prs_used": 4}, decision()),
        ):
            with self.subTest(budget=budget):
                root = new_root(request(), now=100)
                root.update(child)
                updated, action = admit_child(root, candidate, now=101)
                self.assertEqual(updated["state"], "budget-exhausted")
                self.assertEqual(action["kind"], "post_root_status")

        root = new_root(request(), now=100)
        updated, action = admit_child(root, decision(), now=100 + 24 * 60 * 60)
        self.assertEqual(updated["state"], "budget-exhausted")
        self.assertEqual(action["kind"], "post_root_status")

    def test_ambiguous_decision_blocks_on_product_decision_without_parsing_rationale(self) -> None:
        root = new_root(request(), now=100)
        updated, action = admit_child(root, decision(product_ambiguity=True, rationale="ignored"), now=101)

        self.assertEqual(updated["state"], "blocked-on-product-decision")
        self.assertEqual(action["kind"], "post_root_status")

    def test_invalid_artifacts_are_inert_even_when_they_claim_ambiguity_or_staleness(self) -> None:
        invalids = (
            decision(kind="other", product_ambiguity=True),
            decision(schema_version=2, product_ambiguity=True),
            decision(identity={"repository_id": "99", "repository": "other/demo", "pr_number": 42,
                               "head_sha": "b" * 40, "source_key": "github-pr:99:42:" + "b" * 40}, product_ambiguity=True),
            decision(identity={"repository_id": "17", "repository": "allenday/demo", "pr_number": 42,
                               "head_sha": "b" * 40, "source_key": "arbitrary"}, product_ambiguity=True),
            decision(evidence=[{"path": "../secret", "evidence": f"github://allenday/demo/blob/{SHA}/README.md"}], product_ambiguity=True),
        )
        for candidate in invalids:
            with self.subTest(candidate=candidate):
                root = new_root(request(), now=100)
                updated, action = admit_child(root, candidate, now=101)
                self.assertEqual(updated, root)
                self.assertIsNone(action)

    def test_child_digest_changes_when_canonical_docs_impact_identity_changes(self) -> None:
        root = new_root(request(), now=100)
        first, _ = admit_child(root, decision(rationale="First validated finding."), now=101)
        second, _ = admit_child(root, decision(rationale="Second validated finding.", evidence=[
            {"path": "docs/other.md", "evidence": f"github://allenday/demo/blob/{SHA}/docs/other.md"},
        ]), now=102)

        self.assertNotEqual(first["children"][0]["key"], second["children"][0]["key"])

    def test_reconcile_terminalizes_each_terminal_state_deterministically(self) -> None:
        for expected, changes in (
            ("baseline-complete", {"children": [{"state": "complete"}]}),
            ("owner-review-required", {"owner_review_required": True}),
            ("blocked-on-product-decision", {"product_decision_required": True}),
            ("budget-exhausted", {"children_used": 8}),
            ("cancelled", {"cancelled": True}),
        ):
            with self.subTest(expected=expected):
                root = new_root(request(), now=100)
                root.update(changes)
                updated, actions = reconcile_root(root, now=101)
                self.assertEqual(updated["state"], expected)
                self.assertEqual([action["kind"] for action in actions], ["post_root_status"])

    def test_reconcile_reemits_incomplete_persisted_actions_and_stops_after_non_progress_limit(self) -> None:
        root = new_root(request(), now=100)
        root["actions"] = [{"id": "bootstrap-child:x:create_issue", "kind": "create_issue", "state": "pending"}]
        updated, actions = reconcile_root(root, now=101)
        self.assertEqual(actions, root["actions"])
        self.assertEqual(updated["non_progress_count"], 1)

        updated["non_progress_count"] = 2
        exhausted, actions = reconcile_root(updated, now=102)
        self.assertEqual(exhausted["state"], "budget-exhausted")
        self.assertEqual([action["kind"] for action in actions], ["post_root_status"])


if __name__ == "__main__":
    unittest.main()
