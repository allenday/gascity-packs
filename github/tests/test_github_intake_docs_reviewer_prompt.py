from __future__ import annotations

import pathlib
import unittest


class DocsReviewerPromptTests(unittest.TestCase):
    def test_allows_a_strictly_bounded_proposal_ready_review(self) -> None:
        prompt = (
            pathlib.Path(__file__).resolve().parents[1]
            / "agents"
            / "docs-impact-reviewer"
            / "prompt.template.md"
        ).read_text(encoding="utf-8")

        self.assertIn("proposal-ready", prompt)
        self.assertIn("A proposal is allowed only", prompt)
        self.assertIn("complete removed documentation text", prompt)
        self.assertNotIn("This route does not create a\nproposal.", prompt)


if __name__ == "__main__":
    unittest.main()
