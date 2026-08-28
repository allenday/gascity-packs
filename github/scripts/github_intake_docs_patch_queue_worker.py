#!/usr/bin/env python3
"""Consume sanitized TechDocs assignments without network or credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import tempfile
import time
from typing import Any

import github_intake_docs_patch as docs_patch
import github_intake_docs_patch_worker as worker

QUEUE_ARTIFACT_SCHEMA_VERSION = 1


def snapshot_sha256_bytes(raw: bytes) -> str:
    """Digest exact queue bytes, including protocol version and proposal content."""
    return hashlib.sha256(raw).hexdigest()


def snapshot_sha256(snapshot_file: pathlib.Path) -> str:
    return snapshot_sha256_bytes(snapshot_file.read_bytes())


def queue_artifact(snapshot_digest: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": QUEUE_ARTIFACT_SCHEMA_VERSION,
        "snapshot_sha256": snapshot_digest,
        "artifact": docs_patch.validate_agent_review(artifact),
    }


def artifact_is_current(artifact_file: pathlib.Path, raw: bytes) -> bool:
    try:
        assignment = worker.load_assignment_bytes(raw)
        value = json.loads(artifact_file.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "snapshot_sha256", "artifact"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != QUEUE_ARTIFACT_SCHEMA_VERSION
            or value["snapshot_sha256"] != snapshot_sha256_bytes(raw)
            or not isinstance(value["artifact"], dict)
        ):
            return False
        review = docs_patch.validate_agent_review(value["artifact"])
        return review["identity"] == assignment["identity"] and review["agent_skill"] == assignment["agent_skill"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def write_queue_artifact(artifact_file: pathlib.Path, envelope: dict[str, Any]) -> None:
    """Atomically replace stale/corrupt sidecar output with a canonical envelope."""
    artifact_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".docs-patch-queue-", suffix=".tmp", dir=artifact_file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(docs_patch.canonical_json(envelope) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, artifact_file)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def consume_snapshot(
    snapshot_file: pathlib.Path,
    raw: bytes,
    artifact_file: pathlib.Path,
    *,
    adapter_command: str,
    skill_dir: pathlib.Path,
    adapter_timeout_seconds: float = 300.0,
) -> bool:
    """Process precisely the bytes read by the queue scan, never rereading its path."""
    digest = snapshot_sha256_bytes(raw)
    if artifact_is_current(artifact_file, raw):
        return False
    try:
        worker.remove_artifact(artifact_file)
        artifact = worker.review_assignment_bytes(
            raw, adapter_command, skill_dir, adapter_timeout_seconds,
        )
        if artifact is None:
            return False
        write_queue_artifact(artifact_file, queue_artifact(digest, artifact))
        return True
    except (OSError, ValueError):
        return False


def consume_once(
    snapshot_dir: pathlib.Path,
    artifact_dir: pathlib.Path,
    *,
    adapter_command: str | None = None,
    skill_dir: pathlib.Path | None = None,
    adapter_timeout_seconds: float | None = None,
    candidate_dir: pathlib.Path | None = None,
) -> int:
    """Publish completed reviews for assignments lacking a matching envelope."""
    worker.reject_credentials()
    if adapter_command is None:
        adapter_command = os.environ.get("GC_TECHDOCS_ADAPTER_COMMAND", "")
    if skill_dir is None:
        skill_dir = pathlib.Path(os.environ.get("GC_TECHDOCS_SKILL_DIR", ""))
    if adapter_timeout_seconds is None:
        try:
            adapter_timeout_seconds = float(os.environ.get("GC_TECHDOCS_ADAPTER_TIMEOUT_SECONDS", "300"))
        except ValueError:
            adapter_timeout_seconds = 0
    artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handled = 0
    for snapshot_file in sorted(snapshot_dir.glob("*.json")):
        artifact_file = artifact_dir / snapshot_file.name
        # The egress reviewer writes an untrusted raw candidate to its private
        # return directory.  This networkless worker remains the sole local
        # validator/envelope writer; it never invokes a model in this mode.
        if candidate_dir is not None:
            try:
                raw = snapshot_file.read_bytes()
                candidate_file = candidate_dir / snapshot_file.name
                candidate = json.loads(candidate_file.read_text(encoding="utf-8"))
                if not artifact_is_current(artifact_file, raw):
                    review = docs_patch.validate_agent_review(candidate)
                    assignment = worker.load_assignment_bytes(raw)
                    if review["identity"] == assignment["identity"] and review["agent_skill"] == assignment["agent_skill"]:
                        write_queue_artifact(artifact_file, queue_artifact(snapshot_sha256_bytes(raw), review)); handled += 1
                continue
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        try:
            if consume_snapshot(
                snapshot_file,
                snapshot_file.read_bytes(),
                artifact_file,
                adapter_command=adapter_command,
                skill_dir=skill_dir,
                adapter_timeout_seconds=adapter_timeout_seconds,
            ):
                handled += 1
        except OSError:
            # The trusted supervisor will turn absent/invalid output into its
            # human-friendly required-action result; never emit partial output.
            continue
    return handled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", default=os.environ.get("GC_TECHDOCS_SNAPSHOT_DIR", "/work/snapshot"))
    parser.add_argument("--artifact-dir", default=os.environ.get("GC_TECHDOCS_ARTIFACT_DIR", "/work/artifact"))
    parser.add_argument("--adapter-command", default=os.environ.get("GC_TECHDOCS_ADAPTER_COMMAND", ""))
    parser.add_argument("--skill-dir", default=os.environ.get("GC_TECHDOCS_SKILL_DIR", ""))
    parser.add_argument(
        "--adapter-timeout-seconds",
        type=float,
        default=float(os.environ.get("GC_TECHDOCS_ADAPTER_TIMEOUT_SECONDS", "300")),
    )
    parser.add_argument("--poll-seconds", type=float, default=0.2)
    parser.add_argument("--candidate-dir", default=os.environ.get("GC_TECHDOCS_CANDIDATE_DIR", ""))
    args = parser.parse_args()
    snapshot_dir, artifact_dir = pathlib.Path(args.snapshot_dir), pathlib.Path(args.artifact_dir)
    while True:
        consume_once(
            snapshot_dir,
            artifact_dir,
            adapter_command=args.adapter_command,
            skill_dir=pathlib.Path(args.skill_dir),
            adapter_timeout_seconds=args.adapter_timeout_seconds,
            candidate_dir=pathlib.Path(args.candidate_dir) if args.candidate_dir else None,
        )
        time.sleep(max(0.05, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
