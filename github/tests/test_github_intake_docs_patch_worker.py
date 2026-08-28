from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


WORKER = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "github_intake_docs_patch_worker.py"


def assignment(head_sha: str = "a" * 40, changed_paths: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-assignment",
        "identity": {
            "repository_id": "17",
            "repository": "allenday/demo",
            "pr_number": 9,
            "head_sha": head_sha,
            "source_key": "github-pr:17:9:" + head_sha,
        },
        "agent_skill": "developer-experience-techdocs",
        "changed_paths": changed_paths or ["docs/guide.md"],
    }


def review(head_sha: str = "a" * 40, verdict: str = "docs-sufficient") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-review",
        "identity": {
            "repository_id": "17",
            "repository": "allenday/demo",
            "pr_number": 9,
            "head_sha": head_sha,
            "source_key": "github-pr:17:9:" + head_sha,
        },
        "agent_skill": "developer-experience-techdocs",
        "verdict": verdict,
        "rationale": "The changed behavior is adequately documented.",
        "evidence": [{
            "path": "docs/guide.md",
            "evidence": "github://allenday/demo/blob/" + head_sha + "/docs/guide.md",
        }],
        "confidence": 0.92,
        "proposal": None,
    }


def write_adapter(root: pathlib.Path) -> pathlib.Path:
    adapter = root / "city-techdocs-adapter.py"
    adapter.write_text(textwrap.dedent("""\
        import argparse
        import json
        import os
        import pathlib
        import sys

        parser = argparse.ArgumentParser()
        parser.add_argument("--verdict", default="docs-sufficient")
        parser.add_argument("--skill-dir", required=True)
        args = parser.parse_args()
        if os.environ.get("WORKER_TEST_SECRET"):
            raise SystemExit("worker environment leaked to adapter")
        skill = pathlib.Path(args.skill_dir, "SKILL.md").read_text(encoding="utf-8")
        if "developer-experience-techdocs" not in skill:
            raise SystemExit("wrong skill")
        assignment = json.load(sys.stdin)
        identity = assignment["identity"]
        head_sha = identity["head_sha"]
        review = {
            "schema_version": 1,
            "kind": "github-pr-docs-impact-review",
            "identity": identity,
            "agent_skill": assignment["agent_skill"],
            "verdict": args.verdict,
            "rationale": "The configured City TechDocs adapter completed its review.",
            "evidence": [{
                "path": assignment["changed_paths"][0],
                "evidence": "github://" + identity["repository"] + "/blob/" + head_sha + "/" + assignment["changed_paths"][0],
            }],
            "confidence": 0.9,
            "proposal": None,
        }
        json.dump(review, sys.stdout)
    """), encoding="utf-8")
    return adapter


def write_skill(root: pathlib.Path) -> pathlib.Path:
    skill = root / "developer-experience-techdocs"
    skill.mkdir()
    (skill / "SKILL.md").write_text("name: developer-experience-techdocs\n", encoding="utf-8")
    return skill


class DocsPatchWorkerTests(unittest.TestCase):
    def test_worker_passes_only_assignment_and_vendored_skill_to_configured_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignment_file = root / "assignment.json"
            artifact = root / "artifact" / "review.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            adapter, skill = write_adapter(root), write_skill(root)
            environment = {
                **os.environ,
                "WORKER_TEST_SECRET": "must-not-reach-adapter",
            }
            for key in ("GITHUB_TOKEN", "GH_TOKEN"):
                environment.pop(key, None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(WORKER),
                    "--assignment-file",
                    str(assignment_file),
                    "--artifact-file",
                    str(artifact),
                    "--adapter-command",
                    shlex.join([sys.executable, str(adapter)]),
                    "--skill-dir",
                    str(skill),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "completed")
            produced = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(produced["kind"], "github-pr-docs-impact-review")
            self.assertEqual(produced["identity"], assignment()["identity"])
            self.assertEqual(produced["agent_skill"], "developer-experience-techdocs")
            self.assertNotIn("changed_paths", produced)

    def test_unavailable_agent_produces_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignment_file = root / "assignment.json"
            artifact = root / "artifact" / "review.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            artifact.parent.mkdir()
            artifact.write_text('{"stale":true}\n', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(WORKER),
                    "--assignment-file",
                    str(assignment_file),
                    "--artifact-file",
                    str(artifact),
                    "--adapter-command",
                    "/definitely/not/a/city-techdocs-adapter",
                    "--skill-dir",
                    str(write_skill(root)),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"status": "unavailable"})
            self.assertFalse(artifact.exists())

    def test_review_for_another_revision_produces_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            assignment_file = root / "assignment.json"
            artifact = root / "artifact" / "review.json"
            assignment_file.write_text(json.dumps(assignment()), encoding="utf-8")
            adapter = root / "wrong-revision.py"
            adapter.write_text(
                "import json,sys; json.dump(" + repr(review("b" * 40)) + ", sys.stdout)\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(WORKER),
                    "--assignment-file",
                    str(assignment_file),
                    "--artifact-file",
                    str(artifact),
                    "--adapter-command",
                    shlex.join([sys.executable, str(adapter)]),
                    "--skill-dir",
                    str(write_skill(root)),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"status": "unavailable"})
            self.assertFalse(artifact.exists())
