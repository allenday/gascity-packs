#!/usr/bin/env python3
"""Run a configured City TechDocs adapter for one sanitized assignment.

The worker has no GitHub client and does not derive a documentation verdict.
It gives the configured adapter only canonical assignment JSON on stdin and the
vendored TechDocs skill directory, then emits a revision-bound review candidate
only after strict validation. An unavailable or incomplete adapter emits none.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any

import github_intake_docs_patch as docs_patch

ASSIGNMENT_SCHEMA_VERSION = 1
ASSIGNMENT_FIELDS = {"schema_version", "kind", "identity", "agent_skill", "changed_paths"}
ASSIGNMENT_IDENTITY_FIELDS = {"repository_id", "repository", "pr_number", "head_sha", "source_key"}
AGENT_SKILL = "developer-experience-techdocs"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_ADAPTER_OUTPUT_BYTES = 1_048_576
FORBIDDEN_CREDENTIAL_ENV = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_APP_ID",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_APP_PRIVATE_KEY_PEM",
)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} must be non-empty canonical text")
    return value


def validate_assignment(value: Any) -> dict[str, Any]:
    """Return one canonical, revision-bound City TechDocs assignment."""
    if not isinstance(value, dict) or set(value) != ASSIGNMENT_FIELDS:
        raise ValueError("assignment must contain only the documented sanitized fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != ASSIGNMENT_SCHEMA_VERSION:
        raise ValueError(f"assignment schema_version must be {ASSIGNMENT_SCHEMA_VERSION}")
    if value["kind"] != "github-pr-docs-impact-assignment":
        raise ValueError("assignment kind must be github-pr-docs-impact-assignment")
    if value["agent_skill"] != AGENT_SKILL:
        raise ValueError(f"assignment agent_skill must be {AGENT_SKILL}")
    identity = value["identity"]
    if not isinstance(identity, dict) or set(identity) != ASSIGNMENT_IDENTITY_FIELDS:
        raise ValueError("assignment identity must be exact and revision-bound")
    repository_id = _required_text(identity["repository_id"], "identity.repository_id")
    repository = _required_text(identity["repository"], "identity.repository")
    pr_number = identity["pr_number"]
    if type(pr_number) is not int or pr_number <= 0:
        raise ValueError("identity.pr_number must be a positive integer")
    head_sha = _required_text(identity["head_sha"], "identity.head_sha").lower()
    if SHA_PATTERN.fullmatch(head_sha) is None:
        raise ValueError("identity.head_sha must be a lowercase 40-character SHA")
    source_key = _required_text(identity["source_key"], "identity.source_key")
    if source_key != f"github-pr:{repository_id}:{pr_number}:{head_sha}":
        raise ValueError("identity.source_key does not match assignment identity")
    changed_paths = value["changed_paths"]
    if (
        not isinstance(changed_paths, list)
        or len(changed_paths) > 100
        or any(not isinstance(path, str) or not path or path.strip() != path for path in changed_paths)
        or changed_paths != sorted(set(changed_paths))
    ):
        raise ValueError("changed_paths must be a sorted unique list of at most 100 paths")
    return {
        "schema_version": ASSIGNMENT_SCHEMA_VERSION,
        "kind": "github-pr-docs-impact-assignment",
        "identity": {
            "repository_id": repository_id,
            "repository": repository,
            "pr_number": pr_number,
            "head_sha": head_sha,
            "source_key": source_key,
        },
        "agent_skill": AGENT_SKILL,
        "changed_paths": list(changed_paths),
    }


def load_assignment_bytes(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read sanitized assignment: {exc}") from exc
    return validate_assignment(value)


def load_assignment(assignment_file: pathlib.Path) -> dict[str, Any]:
    try:
        return load_assignment_bytes(assignment_file.read_bytes())
    except OSError as exc:
        raise ValueError(f"could not read sanitized assignment: {exc}") from exc


def _adapter_argv(adapter_command: str) -> list[str] | None:
    if not adapter_command.strip():
        return None
    try:
        argv = shlex.split(adapter_command)
    except ValueError:
        return None
    if not argv or any(argument == "--skill-dir" or argument.startswith("--skill-dir=") for argument in argv):
        return None
    return argv


def _adapter_environment() -> dict[str, str]:
    """Supply runtime basics but no caller state, credentials, or City identity."""
    return {
        "HOME": "/tmp",
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }


def run_adapter(
    assignment: dict[str, Any],
    adapter_command: str,
    skill_dir: pathlib.Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any] | None:
    """Return a completed adapter review, or None without inventing a result."""
    argv = _adapter_argv(adapter_command)
    if argv is None or timeout_seconds <= 0 or not (skill_dir / "SKILL.md").is_file():
        return None
    payload = docs_patch.canonical_json(assignment) + "\n"
    try:
        with tempfile.TemporaryDirectory(prefix="city-techdocs-adapter-") as work_dir:
            result = subprocess.run(
                [*argv, "--skill-dir", str(skill_dir)],
                input=payload,
                text=True,
                capture_output=True,
                env=_adapter_environment(),
                cwd=work_dir,
                timeout=timeout_seconds,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout or len(result.stdout.encode("utf-8")) > MAX_ADAPTER_OUTPUT_BYTES:
        return None
    try:
        candidate = json.loads(result.stdout)
        review = docs_patch.validate_agent_review(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if review["identity"] != assignment["identity"] or review["agent_skill"] != assignment["agent_skill"]:
        return None
    return review


def review_assignment_bytes(
    raw: bytes,
    adapter_command: str,
    skill_dir: pathlib.Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any] | None:
    assignment = load_assignment_bytes(raw)
    return run_adapter(assignment, adapter_command, skill_dir, timeout_seconds)


def write_artifact(artifact_file: pathlib.Path, review: dict[str, Any]) -> None:
    """Atomically place only canonical review JSON in the isolated outbox."""
    artifact_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = docs_patch.canonical_json(review) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".docs-review-", suffix=".tmp", dir=artifact_file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, artifact_file)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def remove_artifact(artifact_file: pathlib.Path) -> None:
    try:
        artifact_file.unlink()
    except FileNotFoundError:
        pass


def reject_credentials() -> None:
    leaked = [name for name in FORBIDDEN_CREDENTIAL_ENV if os.environ.get(name)]
    if leaked:
        raise ValueError(f"worker must not receive GitHub credentials: {', '.join(leaked)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assignment-file",
        default=os.environ.get("GC_TECHDOCS_ASSIGNMENT_FILE", os.environ.get("GC_TECHDOCS_SNAPSHOT_FILE", "")),
    )
    parser.add_argument("--artifact-file", default=os.environ.get("GC_TECHDOCS_ARTIFACT_FILE", ""))
    parser.add_argument("--adapter-command", default=os.environ.get("GC_TECHDOCS_ADAPTER_COMMAND", ""))
    parser.add_argument("--skill-dir", default=os.environ.get("GC_TECHDOCS_SKILL_DIR", ""))
    parser.add_argument(
        "--adapter-timeout-seconds",
        type=float,
        default=float(os.environ.get("GC_TECHDOCS_ADAPTER_TIMEOUT_SECONDS", "300")),
    )
    args = parser.parse_args()
    if not args.assignment_file or not args.artifact_file:
        parser.error("--assignment-file and --artifact-file are required")
    artifact_file = pathlib.Path(args.artifact_file)
    try:
        reject_credentials()
        remove_artifact(artifact_file)
        review = review_assignment_bytes(
            pathlib.Path(args.assignment_file).read_bytes(),
            args.adapter_command,
            pathlib.Path(args.skill_dir),
            args.adapter_timeout_seconds,
        )
        if review is None:
            print(docs_patch.canonical_json({"status": "unavailable"}))
            return 0
        write_artifact(artifact_file, review)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(docs_patch.canonical_json({"review_sha256": review["review_sha256"], "status": "completed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
