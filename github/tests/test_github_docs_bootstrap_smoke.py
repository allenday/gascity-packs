from __future__ import annotations

import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_docs_bootstrap import admit_child, new_root, project_actions, reconcile_root, record_child_update


SHA = "a" * 40


def root_request(*, backfill_policy: str = "blocking-only") -> dict[str, object]:
    return {
        "explicit": True,
        "repository_id": "17",
        "repository": "allenday/demo",
        "installation_id": "91",
        "root_issue_number": 42,
        "root_issue_url": "https://github.com/allenday/demo/issues/42",
        "default_branch": "main",
        "default_branch_sha": SHA,
        "domain": "techdocs",
        "role": "developer",
        "job": "install the package",
        "starting_context": "a clone of the repository",
        "success_condition": "the package is installed successfully",
        "backfill_policy": backfill_policy,
        "budgets": {
            "max_depth": 2,
            "max_children": 1,
            "max_docs_prs": 1,
            "max_debt_issues": 1,
            "max_elapsed_seconds": 3600,
            "max_non_progress": 3,
        },
    }


def docs_change_required(*, disposition: str = "blocking") -> dict[str, object]:
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
        "journey_disposition": disposition,
    }


class GraphAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def _resource(self, kind: str, action: dict[str, object]) -> dict[str, str]:
        self.calls.append((kind, str(action["id"])))
        return {"id": f"{kind}-{len(self.calls)}", "logical_id": str(action["id"])}

    def create_issue(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._resource("issue", action)

    def create_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._resource("bead", action)

    def assign_bead(self, root: dict[str, object], action: dict[str, object], child: dict[str, object]) -> dict[str, str]:
        return self._resource("assignment", action)

    def create_docs_pr(self, root: dict[str, object], action: dict[str, object], child: dict[str, object] | None) -> dict[str, str]:
        return self._resource("pr", action)

    def create_debt_issue(self, root: dict[str, object], action: dict[str, object], debt: dict[str, object]) -> dict[str, str]:
        return self._resource("debt", action)

    def post_root_status(self, root: dict[str, object], action: dict[str, object]) -> dict[str, str]:
        return self._resource("status", action)


class DocsBootstrapSmokeTests(unittest.TestCase):
    def test_blocking_journey_projects_one_child_pr_then_terminal_root(self) -> None:
        root, action = admit_child(new_root(root_request(), now=100), docs_change_required(), now=101)
        self.assertEqual(action["kind"], "create_issue")
        adapter = GraphAdapter()

        for _ in range(3):
            root = project_actions(root, adapter)
        child = root["children"][0]
        root, pr_action = record_child_update(root, {
            "schema_version": 1,
            "kind": "github-docs-bootstrap-child-update",
            "admitted_child": child,
            "state": "complete",
            "idd_update": {"phase": "ready_to_close", "change_set": "none", "revision": "none", "evidence": ["run:1"], "summary": "done"},
            "documentation_pr": {"branch": "gas-city/docs-bootstrap", "title": "Fix install docs", "body": "Bounded update."},
        })
        self.assertEqual(pr_action["kind"], "create_docs_pr")
        root = project_actions(root, adapter)
        root, terminal_actions = reconcile_root(root, now=102)

        self.assertEqual(root["state"], "baseline-complete")
        self.assertEqual(root["docs_prs_used"], 1)
        self.assertEqual([kind for kind, _ in adapter.calls], ["issue", "bead", "assignment", "pr"])
        self.assertEqual([action["kind"] for action in terminal_actions], ["post_root_status"])

    def test_nonblocking_record_debt_stays_a_single_inactive_leaf(self) -> None:
        root, action = admit_child(
            new_root(root_request(backfill_policy="record-debt"), now=100),
            docs_change_required(disposition="non-blocking"),
            now=101,
        )
        adapter = GraphAdapter()
        root = project_actions(root, adapter)
        replayed, duplicate = admit_child(root, docs_change_required(disposition="non-blocking"), now=102)

        self.assertEqual(action["kind"], "create_debt_issue")
        self.assertIsNone(duplicate)
        self.assertEqual(len(replayed["debts"]), 1)
        self.assertEqual(replayed["children"], [])
        self.assertEqual([kind for kind, _ in adapter.calls], ["debt"])
        self.assertFalse(any(action["kind"] in {"create_issue", "create_bead", "assign_bead", "create_docs_pr"} for action in replayed["actions"]))

    def test_ordinary_pr_decision_cannot_create_a_bootstrap_root(self) -> None:
        with self.assertRaises(ValueError):
            new_root(docs_change_required()["artifact"], now=100)


if __name__ == "__main__":
    unittest.main()
