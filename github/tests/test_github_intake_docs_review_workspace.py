from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TOOL = SCRIPTS / "github_intake_docs_review_workspace.py"
sys.path.insert(0, str(SCRIPTS))

import github_intake_docs_patch as docs_patch
from github.tests.test_github_intake_docs_patch_worker import assignment


class DocsReviewWorkspaceTests(unittest.TestCase):
    def test_submit_generates_valid_proposal_from_staged_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            assignment_file = root / "assignment.json"
            workspace = root / "workspace"
            candidate = root / "candidate.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")

            initialized = subprocess.run(
                [sys.executable, str(TOOL), "init", "--assignment-file", str(assignment_file), "--workspace", str(workspace)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            (workspace / "docs").mkdir()
            (workspace / "docs" / "guide.md").write_text("# Guide\n\nUpdated developer guidance.\n", encoding="utf-8")
            staged = subprocess.run(
                ["git", "add", "docs/guide.md"], cwd=workspace, text=True, capture_output=True, check=False,
            )
            self.assertEqual(staged.returncode, 0, staged.stderr)

            submitted = subprocess.run(
                [
                    sys.executable, str(TOOL), "submit", "--assignment-file", str(assignment_file),
                    "--workspace", str(workspace), "--candidate-file", str(candidate),
                    "--verdict", "proposal-ready", "--rationale", "The staged guide documents the changed behavior.",
                    "--confidence", "0.9", "--evidence-path", "docs/guide.md",
                ], text=True, capture_output=True, check=False,
            )
            self.assertEqual(submitted.returncode, 0, submitted.stderr)
            envelope = json.loads(candidate.read_text(encoding="utf-8"))
            review = docs_patch.validate_agent_review(envelope["artifact"])
            proposal = review["proposal"]
            self.assertEqual(review["verdict"], "proposal-ready")
            self.assertIn("diff --git a/docs/guide.md b/docs/guide.md", proposal["diff"])
            self.assertEqual(proposal["files"][0]["path"], "docs/guide.md")


if __name__ == "__main__":
    unittest.main()
