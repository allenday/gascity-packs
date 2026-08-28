from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_impact as docs_impact


class DocsImpactTests(unittest.TestCase):
    def test_classify_paths_is_conservative_for_product_change_without_docs(self) -> None:
        self.assertEqual(
            docs_impact.classify_paths(["github/scripts/github_intake_common.py", "github/tests/test_common.py"])[0],
            "needs-human-decision",
        )

    def test_classify_paths_passes_non_product_change(self) -> None:
        self.assertEqual(docs_impact.classify_paths([".github/workflows/test.yml"])[0], "no-impact")

    def test_evaluate_creates_and_completes_check_for_exact_revision(self) -> None:
        payload = {
            "repository": {"id": 17, "full_name": "allenday/demo", "name": "demo", "owner": {"login": "allenday"}},
            "pull_request": {"number": 9, "html_url": "https://github.com/allenday/demo/pull/9", "head": {"sha": "a" * 40}},
            "installation": {"id": 44},
        }
        with mock.patch.object(docs_impact, "create_source", return_value={"status": "created", "bead_id": "ga-1"}), mock.patch.object(
            docs_impact.common, "create_check_run_with_token", return_value={"id": 81}
        ) as create_check, mock.patch.object(
            docs_impact.common, "list_pull_request_files_with_token", return_value=[{"filename": ".github/workflows/test.yml"}]
        ), mock.patch.object(docs_impact.common, "update_check_run_with_token", return_value={"id": 81, "conclusion": "success"}) as update_check:
            result = docs_impact.evaluate(payload, "delivery-1", "token")

        self.assertEqual(result["outcome"], "no-impact")
        self.assertEqual(create_check.call_args.args[3], "a" * 40)
        self.assertEqual(update_check.call_args.args[3], 81)
        self.assertEqual(update_check.call_args.args[5], "success")
