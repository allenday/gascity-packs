#!/usr/bin/env python3
"""Prepare and publish a bounded City documentation-review workspace."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

import github_intake_docs_patch as docs_patch
import github_intake_docs_patch_worker as worker


def _git(workspace: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=workspace, text=True, capture_output=True, check=False,
        env={"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1"},
    )


def _require_git(workspace: pathlib.Path, *args: str) -> str:
    result = _git(workspace, *args)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def initialize_workspace(assignment: dict[str, Any], workspace: pathlib.Path) -> None:
    """Create an empty, per-revision Git index for a safe docs proposal."""
    if workspace.exists() and any(workspace.iterdir()):
        evidence = workspace / "EVIDENCE.json"
        if (
            (workspace / ".git").is_dir()
            and evidence.is_file()
            and evidence.read_text(encoding="utf-8") == docs_patch.canonical_json(assignment) + "\n"
        ):
            return
        raise ValueError("review workspace already exists with different contents")
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_git(workspace, "init", "--quiet")
    _require_git(workspace, "config", "core.hooksPath", "/dev/null")
    evidence = workspace / "EVIDENCE.json"
    evidence.write_text(docs_patch.canonical_json(assignment) + "\n", encoding="utf-8")
    evidence.chmod(0o400)
    readme = workspace / "README"
    readme.write_text(
        "This is a disposable, offline documentation proposal workspace.\n"
        "Read EVIDENCE.json; do not alter it. Create or restore only documentation files,\n"
        "then stage them with git add. The submit tool derives the patch from the Git index.\n",
        encoding="utf-8",
    )
    readme.chmod(0o400)


def _staged_paths(workspace: pathlib.Path) -> list[str]:
    raw = _require_git(workspace, "diff", "--cached", "--name-only", "-z", "--no-renames")
    paths = [item for item in raw.split("\0") if item]
    if not paths:
        raise ValueError("no staged documentation changes")
    return paths


def _proposal(assignment: dict[str, Any], workspace: pathlib.Path, evidence_path: str) -> dict[str, Any]:
    evidence_files = {item["path"]: item for item in assignment["evidence_bundle"]["files"]}
    if evidence_path not in evidence_files:
        raise ValueError("evidence path is not present in the assignment")
    paths = _staged_paths(workspace)
    diff_check = _git(workspace, "diff", "--cached", "--check", "--no-ext-diff", "--no-renames")
    if diff_check.returncode:
        raise ValueError(diff_check.stdout.strip() or diff_check.stderr.strip() or "staged diff check failed")
    diff = _require_git(workspace, "diff", "--cached", "--no-ext-diff", "--no-renames", "--binary")
    files: list[dict[str, str]] = []
    for path in paths:
        docs_patch._validate_path(path)
        content = _require_git(workspace, "show", f":{path}").encode("utf-8")
        files.append({"path": path, "sha256": hashlib.sha256(content).hexdigest()})
    identity = assignment["identity"]
    reference = evidence_files[evidence_path]["reference"]
    return {
        "schema_version": 1,
        "status": "proposed",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "identity": assignment["evidence_bundle"]["proposal_identity"],
        "patch_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "diff": diff,
        "files": files,
        "claims": [{
            "claim": "The staged documentation proposal is limited to the documented pull-request impact.",
            "evidence": reference,
            "release_scope": f"pull request #{identity['pr_number']} at {identity['head_sha']}",
        }],
        "checks": [{
            "command": "git diff --cached --check --no-ext-diff --no-renames",
            "status": "passed",
            "explanation": "Git accepted the staged documentation patch without whitespace errors.",
        }],
    }


def _atomic_write(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".docs-review-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(docs_patch.canonical_json(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def submit_review(
    raw_assignment: bytes, workspace: pathlib.Path, candidate_file: pathlib.Path, *,
    verdict: str, rationale: str, confidence: float, evidence_path: str,
) -> dict[str, Any]:
    assignment = worker.load_assignment_bytes(raw_assignment)
    proposal = _proposal(assignment, workspace, evidence_path) if verdict == "proposal-ready" else None
    review = {
        "schema_version": 1,
        "kind": "github-pr-docs-impact-review",
        "identity": assignment["identity"],
        "agent_skill": assignment["agent_skill"],
        "verdict": verdict,
        "rationale": rationale,
        "evidence": [{"path": evidence_path, "evidence": next(
            item["reference"] for item in assignment["evidence_bundle"]["files"] if item["path"] == evidence_path
        )}],
        "confidence": confidence,
        "proposal": proposal,
    }
    validated = docs_patch.validate_agent_review(review)
    envelope = {
        "schema_version": 1,
        "snapshot_sha256": hashlib.sha256(raw_assignment).hexdigest(),
        "artifact": validated,
    }
    _atomic_write(candidate_file, envelope)
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--assignment-file", required=True)
    initialize.add_argument("--workspace", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--assignment-file", required=True)
    submit.add_argument("--workspace", required=True)
    submit.add_argument("--candidate-file", required=True)
    submit.add_argument("--verdict", required=True)
    submit.add_argument("--rationale", required=True)
    submit.add_argument("--confidence", required=True, type=float)
    submit.add_argument("--evidence-path", required=True)
    args = parser.parse_args()
    try:
        raw = pathlib.Path(args.assignment_file).read_bytes()
        assignment = worker.load_assignment_bytes(raw)
        if args.command == "init":
            initialize_workspace(assignment, pathlib.Path(args.workspace))
            return 0
        submit_review(
            raw, pathlib.Path(args.workspace), pathlib.Path(args.candidate_file),
            verdict=args.verdict, rationale=args.rationale, confidence=args.confidence,
            evidence_path=args.evidence_path,
        )
        return 0
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
