from __future__ import annotations

import pathlib
import re
import tomllib
import unittest


GITHUB_ROOT = pathlib.Path(__file__).resolve().parents[1]


class VendoredSkillsTests(unittest.TestCase):
    def test_issue_driven_development_skill_has_complete_pinned_provenance(self) -> None:
        """Missing local IDD instructions or mutable provenance must be rejected."""
        skill_root = GITHUB_ROOT / "skills" / "managing-issue-driven-development"
        required_files = (
            skill_root / "SKILL.md",
            skill_root / "references" / "protocol.md",
            skill_root / "references" / "github.md",
            skill_root / "references" / "github-actions.md",
            skill_root / "references" / "gitea.md",
            skill_root / "references" / "woodpecker.md",
            skill_root / "agents" / "openai.yaml",
        )

        for required_file in required_files:
            self.assertTrue(required_file.is_file(), required_file)

        provenance = tomllib.loads(
            (GITHUB_ROOT / "vendor" / "personal-agent-skills" / "upstream.toml").read_text(
                encoding="utf-8"
            )
        )["managing_issue_driven_development"]
        self.assertEqual(
            provenance["repository"],
            "https://github.com/allenday/personal-agent-skills.git",
        )
        self.assertRegex(provenance["revision"], re.compile(r"^[0-9a-f]{40}$"))
        self.assertEqual(provenance["path"], "skills/managing-issue-driven-development")
        self.assertEqual(provenance["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
