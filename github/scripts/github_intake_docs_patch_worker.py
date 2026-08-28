#!/usr/bin/env python3
"""Produce one canonical documentation-patch artifact from a sanitized snapshot.

This program intentionally has no GitHub client. The trusted supervisor creates
the snapshot and later validates/publishes the resulting artifact; this worker
only validates and canonicalizes the proposal supplied in the snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
from typing import Any

import github_intake_docs_patch as docs_patch

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_FIELDS = {"schema_version", "proposal"}
SNAPSHOT_CONTEXT_FIELDS = SNAPSHOT_FIELDS | {"identity", "changed_paths"}
FORBIDDEN_CREDENTIAL_ENV = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_APP_ID",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_APP_PRIVATE_KEY_PEM",
)


def load_snapshot_bytes(raw: bytes) -> dict[str, Any]:
    """Validate one already-read snapshot byte sequence into a canonical artifact."""
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read sanitized snapshot: {exc}") from exc
    if not isinstance(value, dict) or (set(value) != SNAPSHOT_FIELDS and set(value) != SNAPSHOT_CONTEXT_FIELDS):
        raise ValueError("snapshot must contain only the documented sanitized fields")
    if value.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"snapshot schema_version must be {SNAPSHOT_SCHEMA_VERSION}")
    proposal = value.get("proposal")
    if not isinstance(proposal, dict):
        raise ValueError("snapshot proposal must be an object")
    return docs_patch.validate_artifact(proposal)


def load_snapshot(snapshot_file: pathlib.Path) -> dict[str, Any]:
    """Load the narrow worker input contract and return its canonical artifact."""
    try:
        return load_snapshot_bytes(snapshot_file.read_bytes())
    except OSError as exc:
        raise ValueError(f"could not read sanitized snapshot: {exc}") from exc


def write_artifact(artifact_file: pathlib.Path, artifact: dict[str, Any]) -> None:
    """Atomically place only canonical JSON in the isolated artifact outbox."""
    artifact_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = docs_patch.canonical_json(artifact) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".docs-patch-", suffix=".tmp", dir=artifact_file.parent)
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


def reject_credentials() -> None:
    leaked = [name for name in FORBIDDEN_CREDENTIAL_ENV if os.environ.get(name)]
    if leaked:
        raise ValueError(f"worker must not receive GitHub credentials: {', '.join(leaked)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-file", default=os.environ.get("GC_TECHDOCS_SNAPSHOT_FILE", ""))
    parser.add_argument("--artifact-file", default=os.environ.get("GC_TECHDOCS_ARTIFACT_FILE", ""))
    args = parser.parse_args()
    if not args.snapshot_file or not args.artifact_file:
        parser.error("--snapshot-file and --artifact-file are required")
    try:
        reject_credentials()
        artifact = load_snapshot(pathlib.Path(args.snapshot_file))
        write_artifact(pathlib.Path(args.artifact_file), artifact)
    except ValueError as exc:
        parser.error(str(exc))
    print(docs_patch.canonical_json({"artifact_sha256": artifact["artifact_sha256"], "status": artifact["status"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
