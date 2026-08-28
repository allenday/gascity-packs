#!/usr/bin/env python3
"""Consume sanitized TechDocs queue snapshots without network or credentials."""

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


def snapshot_sha256(snapshot_file: pathlib.Path) -> str:
    """Digest exact queue bytes, including protocol version and proposal content."""
    return hashlib.sha256(snapshot_file.read_bytes()).hexdigest()


def queue_artifact(snapshot_file: pathlib.Path, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": QUEUE_ARTIFACT_SCHEMA_VERSION,
        "snapshot_sha256": snapshot_sha256(snapshot_file),
        "artifact": docs_patch.validate_artifact(artifact),
    }


def artifact_is_current(artifact_file: pathlib.Path, digest: str) -> bool:
    try:
        value = json.loads(artifact_file.read_text(encoding="utf-8"))
        return (
            isinstance(value, dict)
            and set(value) == {"schema_version", "snapshot_sha256", "artifact"}
            and value["schema_version"] == QUEUE_ARTIFACT_SCHEMA_VERSION
            and value["snapshot_sha256"] == digest
            and isinstance(value["artifact"], dict)
            and docs_patch.validate_artifact(value["artifact"])
        )
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


def consume_once(snapshot_dir: pathlib.Path, artifact_dir: pathlib.Path) -> int:
    """Publish every queued snapshot lacking a valid matching output envelope."""
    worker.reject_credentials()
    artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handled = 0
    for snapshot_file in sorted(snapshot_dir.glob("*.json")):
        artifact_file = artifact_dir / snapshot_file.name
        digest = snapshot_sha256(snapshot_file)
        if artifact_is_current(artifact_file, digest):
            continue
        try:
            write_queue_artifact(artifact_file, queue_artifact(snapshot_file, worker.load_snapshot(snapshot_file)))
            handled += 1
        except ValueError:
            # The trusted supervisor will turn absent/invalid output into its
            # human-friendly required-action result; never emit partial output.
            continue
    return handled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", default=os.environ.get("GC_TECHDOCS_SNAPSHOT_DIR", "/work/snapshot"))
    parser.add_argument("--artifact-dir", default=os.environ.get("GC_TECHDOCS_ARTIFACT_DIR", "/work/artifact"))
    parser.add_argument("--poll-seconds", type=float, default=0.2)
    args = parser.parse_args()
    snapshot_dir, artifact_dir = pathlib.Path(args.snapshot_dir), pathlib.Path(args.artifact_dir)
    while True:
        consume_once(snapshot_dir, artifact_dir)
        time.sleep(max(0.05, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
