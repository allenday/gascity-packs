from __future__ import annotations

import pathlib
import unittest


class DocsReviewerPromptTests(unittest.TestCase):
    def test_uses_a_workspace_and_tool_generated_proposal(self) -> None:
        prompt = (
            pathlib.Path(__file__).resolve().parents[1]
            / "agents"
            / "docs-impact-reviewer"
            / "prompt.template.md"
        ).read_text(encoding="utf-8")

        self.assertIn("proposal-ready", prompt)
        self.assertIn("git diff --cached", prompt)
        self.assertIn("github_intake_docs_review_workspace.py submit", prompt)
        self.assertIn("Do not hand-write a diff", prompt)
        self.assertIn(
            "full deletion of a documentation file is immutable evidence",
            prompt,
        )
        self.assertIn(
            "restoring its exact deleted content",
            prompt,
        )
        self.assertNotIn("write the proposed unified-diff text exactly", prompt)


if __name__ == "__main__":
    unittest.main()
