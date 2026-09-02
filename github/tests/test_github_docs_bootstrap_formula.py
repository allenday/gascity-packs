from __future__ import annotations

import copy
import pathlib
import re
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

    def _assert_required_journey_and_budgets_have_no_defaults(self, formula: dict[str, object]) -> None:
        variables = formula["vars"]
        for name in (
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
            if variables[name].get("required") is not True:
                self.fail(f"{name} must be required")
            if "default" in variables[name]:
                self.fail(f"{name} must not define a default")

    def _assert_worker_operational_authority(self, prompt: str) -> None:
        normalized = " ".join(prompt.lower().split())
        self.assertRegex(
            normalized,
            r"\bdo not\b[^.]*\b(?:write|push)\b[^.]*\b(?:author|contributor)\b[^.]*\bbranch\b",
        )
        self.assertRegex(normalized, r"\bdo not merge\b[^.]*\bpull request\b")
        self.assertEqual(
            re.findall(r"\b(?:may|can) create at most (\w+) app-owned documentation pull request\b", normalized),
            ["one"],
        )
        self.assertNotRegex(
            normalized,
            r"\b(?:may|can|allowed to)\b[^.]*\b(?:write|push)\b[^.]*\b(?:author|contributor)\b[^.]*\bbranch\b",
        )
        self.assertNotRegex(normalized, r"\b(?:may|can|allowed to)\b[^.]*\bmerge\b")

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

        self._assert_required_journey_and_budgets_have_no_defaults(formula)
        self.assertNotIn("contract", formula)
        self.assertNotIn("pull_request", variables)
        self.assertNotIn("pr_number", variables)
        self.assertNotIn("head_sha", variables)

    def test_formula_rejects_defaults_without_owning_journey_value_validation(self) -> None:
        formula = self._formula()
        self._assert_required_journey_and_budgets_have_no_defaults(formula)

        cases = (
            ("default budget", lambda value: value["vars"]["max_children"].update(default="8")),
            ("default journey field", lambda value: value["vars"]["techdocs_role"].update(default="reader")),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                invalid = copy.deepcopy(formula)
                mutate(invalid)
                with self.assertRaises(AssertionError):
                    self._assert_required_journey_and_budgets_have_no_defaults(invalid)

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

    def test_worker_authority_allows_only_one_app_owned_documentation_pr(self) -> None:
        prompt = self._worker_prompt()
        self._assert_worker_operational_authority(prompt)

        cases = (
            ("author branch write", lambda value: re.sub(r"Do not write or push to\s+an author or contributor branch\.", "You may write to an author branch.", value)),
            ("contributor branch write", lambda value: re.sub(r"Do not write or push to\s+an author or contributor branch\.", "You may push to a contributor branch.", value)),
            ("merge", lambda value: value.replace("Do not merge a pull request.", "You may merge a pull request.")),
            ("second documentation PR", lambda value: value.replace("at most one App-owned documentation pull request", "at most two App-owned documentation pull requests")),
            ("non-App PR owner", lambda value: value.replace("App-owned documentation pull request", "worker-owned documentation pull request")),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                invalid = mutate(prompt)
                with self.assertRaises(AssertionError):
                    self._assert_worker_operational_authority(invalid)

    def test_agent_metadata_is_rig_scoped_and_not_a_fallback(self) -> None:
        metadata = tomllib.loads((AGENT_ROOT / "agent.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["description"], "GitHub explicit-root documentation bootstrap worker")
        self.assertEqual(metadata["scope"], "rig")
        self.assertFalse(metadata["fallback"])


if __name__ == "__main__":
    unittest.main()
