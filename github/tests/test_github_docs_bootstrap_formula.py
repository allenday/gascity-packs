from __future__ import annotations

import pathlib
import tomllib
import unittest


GITHUB_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_PATH = GITHUB_ROOT / "formulas" / "github-docs-bootstrap.formula.toml"
AGENT_ROOT = GITHUB_ROOT / "agents" / "docs-bootstrap"


class DocsBootstrapFormulaTests(unittest.TestCase):
    def _formula(self) -> dict[str, object]:
        return tomllib.loads(FORMULA_PATH.read_text(encoding="utf-8"))

    def _worker_prompt(self) -> str:
        return (AGENT_ROOT / "prompt.template.md").read_text(encoding="utf-8")

    def test_formula_requires_an_explicit_root_with_complete_journey_and_budget_contract(self) -> None:
        formula = self._formula()
        variables = formula["vars"]

        for name in (
            "repository",
            "installation_id",
            "root_issue_url",
            "root_issue_number",
            "default_branch_sha",
            "techdocs_role",
            "techdocs_job",
            "techdocs_starting_context",
            "techdocs_success_condition",
            "techdocs_backfill_policy",
            "max_depth",
            "max_children",
            "max_docs_prs",
            "max_debt_issues",
            "max_elapsed_seconds",
            "max_non_progress",
        ):
            with self.subTest(variable=name):
                self.assertTrue(variables[name]["required"])

        self.assertNotIn("pull_request", variables)
        self.assertNotIn("pr_number", variables)
        self.assertNotIn("head_sha", variables)

    def test_formula_runs_only_the_explicit_root_lifecycle(self) -> None:
        steps = self._formula()["steps"]
        self.assertEqual(
            [step["id"] for step in steps],
            [
                "load-explicit-root",
                "snapshot-and-admit",
                "project",
                "run-admitted-child",
                "reconcile",
                "terminal-status",
            ],
        )
        text = "\n".join(step["description"] for step in steps).lower()
        self.assertIn("explicit root", text)
        self.assertIn("github_docs_bootstrap.py", text)
        self.assertIn("managing-issue-driven-development", text)
        self.assertIn("developer-experience-techdocs", text)
        self.assertIn("non-blocking", text)
        self.assertIn("must not invoke the worker", text)
        self.assertNotIn("pull_request", text)

    def test_worker_requires_qualified_admitted_child_provenance(self) -> None:
        prompt = self._worker_prompt()
        for field in (
            "bootstrap_identity",
            "snapshot_sha",
            "decision_identity",
            "decision_digest",
            "root_issue_url",
            "parent_issue_url",
            "evidence_paths",
        ):
            with self.subTest(field=field):
                self.assertIn(field, prompt)
        self.assertIn("one admitted child record", prompt.lower())
        self.assertIn("idd-compliant child update", prompt.lower())

    def test_worker_cannot_write_an_author_branch_or_merge(self) -> None:
        prompt = self._worker_prompt().lower()
        for forbidden in (
            "git push",
            "git merge",
            "author branch",
            "merge the pull request",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, prompt)
        self.assertIn("at most one app-owned documentation pull request", prompt)
        self.assertIn("do not merge", prompt)

    def test_agent_metadata_is_rig_scoped_and_not_a_fallback(self) -> None:
        metadata = tomllib.loads((AGENT_ROOT / "agent.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["description"], "GitHub explicit-root documentation bootstrap worker")
        self.assertEqual(metadata["scope"], "rig")
        self.assertFalse(metadata["fallback"])


if __name__ == "__main__":
    unittest.main()
