from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


WORKER = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "github_intake_docs_patch_worker.py"

DIFF = """diff --git a/docs/guide.md b/docs/guide.md
index 1111111..2222222 100644
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1 +1 @@
-Old guidance.
+New guidance.
"""


def proposal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "proposed",
        "generated_at": "2026-08-28T12:00:00Z",
        "identity": {
            "repository_id": "17", "repository": "allenday/demo", "pr_number": 9,
            "base_sha": "b" * 40, "head_sha": "a" * 40,
            "head_repository_id": "17", "head_repository": "allenday/demo", "base_ref": "main",
        },
        "patch_sha256": hashlib.sha256(DIFF.encode("utf-8")).hexdigest(),
        "diff": DIFF,
        "files": [{"path": "docs/guide.md", "sha256": "c" * 64}],
        "claims": [{
            "claim": "Guide token github_pat_abcdefghijklmnopqrstuvwxyz123456 is redacted.",
            "evidence": "github://allenday/demo/blob/" + "a" * 40 + "/README.md",
            "release_scope": "unreleased",
        }],
        "checks": [{"command": "make docs-check", "status": "passed", "explanation": "Documentation checks passed."}],
    }


class DocsPatchWorkerTests(unittest.TestCase):
    def test_worker_canonicalizes_sanitized_snapshot_without_github_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            snapshot = root / "snapshot.json"
            artifact = root / "artifact" / "proposal.json"
            snapshot.write_text(json.dumps({"schema_version": 1, "proposal": proposal()}), encoding="utf-8")
            environment = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_") and key != "GH_TOKEN"}
            result = subprocess.run(
                [sys.executable, str(WORKER), "--snapshot-file", str(snapshot), "--artifact-file", str(artifact)],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            produced = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(produced["patch_sha256"], hashlib.sha256(DIFF.encode("utf-8")).hexdigest())
            self.assertEqual(produced["identity"]["head_sha"], "a" * 40)
            self.assertEqual(produced["claims"][0]["claim"], "Guide token [REDACTED] is redacted.")
            self.assertNotIn("github_pat_abcdefghijklmnopqrstuvwxyz123456", artifact.read_text(encoding="utf-8"))
