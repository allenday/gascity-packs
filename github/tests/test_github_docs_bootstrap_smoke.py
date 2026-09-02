from __future__ import annotations

import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from github_docs_bootstrap import begin_journey, new_journey, project_actions, reconcile_root, record_child_update


SHA = "a" * 40


def journey_request(
    *, source: dict[str, object] | None = None, backfill_policy: str = "blocking-only", documentation_index: str | None = None,
) -> dict[str, object]:
    root: dict[str, object] = {
        "repository_id": "17",
        "repository": "allenday/demo",
        "installation_id": "91",
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
    if documentation_index is not None:
        root["documentation_index"] = documentation_index
    root["source"] = source or {
        "kind": "github-issue",
        "key": "github-issue:17:42",
        "url": "https://github.com/allenday/demo/issues/42",
        "issue_number": 42,
        "projection_capabilities": ["issue-comment"],
    }
    return root


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
    def test_docs_index_journey_projects_one_child_pr_then_terminal(self) -> None:
        root, action = begin_journey(
            journey_request(documentation_index="docs/index.md"), docs_change_required(), now=101,
        )
        assert root is not None and action is not None
        self.assertEqual(action["kind"], "create_issue")
        self.assertEqual(root["documentation_root"], "docs/index.md")
        adapter = GraphAdapter()

        for _ in range(3):
            root = project_actions(root, adapter)
        child = root["children"][0]
        root, pr_action = record_child_update(root, {
            "schema_version": 1,
            "kind": "github-docs-journey-child-update",
            "admitted_child": child,
            "state": "complete",
            "idd_update": {"phase": "ready_to_close", "change_set": "none", "revision": "none", "evidence": ["run:1"], "summary": "done"},
            "documentation_branch": {"branch": "gas-city/docs-bootstrap", "evidence": ["commit:abcdef"]},
        })
        self.assertEqual(pr_action["kind"], "create_docs_pr")
        root = project_actions(root, adapter)
        root, terminal_actions = reconcile_root(root, now=102)

        self.assertEqual(root["state"], "baseline-complete")
        self.assertEqual(root["docs_prs_used"], 1)
        self.assertEqual([kind for kind, _ in adapter.calls], ["issue", "bead", "assignment", "pr"])
        self.assertEqual([action["kind"] for action in terminal_actions], ["post_root_status"])

    def test_readme_fallback_and_nonblocking_debt_stay_inactive(self) -> None:
        request = journey_request(backfill_policy="record-debt")
        self.assertEqual(new_journey(request, now=100)["documentation_root"], "README.md")
        root, action = begin_journey(
            request, docs_change_required(disposition="non-blocking"), now=101,
        )
        assert root is not None and action is not None
        adapter = GraphAdapter()
        root = project_actions(root, adapter)
        replayed, duplicate = begin_journey(
            request, docs_change_required(disposition="non-blocking"), now=102, existing_journey=root,
        )
        assert replayed is not None

        self.assertEqual(action["kind"], "create_debt_issue")
        self.assertIsNone(duplicate)
        self.assertEqual(len(replayed["debts"]), 1)
        self.assertEqual(replayed["children"], [])
        self.assertEqual([kind for kind, _ in adapter.calls], ["debt"])
        self.assertFalse(any(action["kind"] in {"create_issue", "create_bead", "assign_bead", "create_docs_pr"} for action in replayed["actions"]))

    def test_generic_source_cannot_expand_another_journey(self) -> None:
        request = journey_request()
        journey, action = begin_journey(request, docs_change_required(), now=101)
        assert journey is not None and action is not None
        foreign_request = journey_request(source={
            "kind": "generic", "key": "external:other", "url": "urn:external:other", "projection_capabilities": [],
        })

        continued, foreign_action = begin_journey(
            foreign_request, docs_change_required(), now=102, existing_journey=journey,
        )

        self.assertIsNone(continued)
        self.assertIsNone(foreign_action)


if __name__ == "__main__":
    unittest.main()
