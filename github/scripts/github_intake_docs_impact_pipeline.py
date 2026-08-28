#!/usr/bin/env python3
"""Run the trusted PR handoff around the isolated, tokenless TechDocs worker.

This program deliberately does not generate documentation prose.  A TechDocs
producer may place a proposal for the exact revision in its private proposal
inbox; this supervisor snapshots that proposal plus a bounded list of changed
paths, runs the tokenless worker, and gives only its artifact to the trusted
Check Run projector.  In the absence of a proposal it still publishes a clear
human review result instead of pretending that an artifact exists.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any, Callable

import github_intake_common as common
import github_intake_docs_impact as docs_impact
import github_intake_service as service


def changed_paths(token: str, context: dict[str, str]) -> list[str]:
    files = common.list_pull_request_files_with_token(token, context["owner"], context["repo"], context["number"])
    paths = [str(file.get("filename", "")).strip() for file in files]
    return sorted({path for path in paths if path})


def proposal_inbox_path(context: dict[str, str]) -> pathlib.Path:
    root = pathlib.Path(os.environ.get("GC_GITHUB_DOCS_PATCH_PROPOSAL_DIR", pathlib.Path(common.data_dir()) / "docs-patch-proposals"))
    return root / f"{common.safe_storage_id(service.github_pr_source_key(context), 'proposal')}.json"


def read_proposal(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(value, dict) and isinstance(value.get("proposal"), dict):
        return value["proposal"]
    return value if isinstance(value, dict) else None


def job_name(context: dict[str, str]) -> str:
    """Stable queue identity for one immutable pull-request head."""
    return common.safe_storage_id(service.github_pr_source_key(context), "docs-patch-handoff")


def snapshot_sha256(snapshot_file: pathlib.Path) -> str:
    import hashlib
    return hashlib.sha256(snapshot_file.read_bytes()).hexdigest()


def unwrap_current_artifact(snapshot_file: pathlib.Path, value: Any) -> dict[str, Any] | None:
    """Reject output unless its protocol version and digest match this job exactly."""
    if not isinstance(value, dict):
        return None
    if set(value) != {"schema_version", "snapshot_sha256", "artifact"}:
        return None
    if value.get("schema_version") != 1 or value.get("snapshot_sha256") != snapshot_sha256(snapshot_file):
        return None
    artifact = value.get("artifact")
    return artifact if isinstance(artifact, dict) else None


def wait_for_sidecar_artifact(snapshot_file: pathlib.Path, artifact_file: pathlib.Path) -> dict[str, Any] | None:
    """Consume only the artifact produced for this revision-bound queue item."""
    timeout = max(0.0, float(os.environ.get("GC_GITHUB_DOCS_PATCH_WAIT_SECONDS", "15")))
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        value = common.read_json(artifact_file, None)
        artifact = unwrap_current_artifact(snapshot_file, value)
        if artifact is not None:
            return artifact
        time.sleep(0.1)
    return None


def run_handoff(
    payload: dict[str, Any], delivery_id: str, token: str, proposal_file: pathlib.Path | None,
    snapshot_dir: pathlib.Path, artifact_dir: pathlib.Path,
    wait_for_artifact: Callable[[pathlib.Path, pathlib.Path], dict[str, Any] | None] = wait_for_sidecar_artifact,
) -> dict[str, Any]:
    """Enqueue a safe worker handoff and project its sidecar artifact for this SHA."""
    context = service.github_pr_context(payload)
    paths = changed_paths(token, context)
    proposal = read_proposal(proposal_file)
    artifact: dict[str, Any] | None = None
    if proposal is not None:
        snapshot_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = job_name(context)
        snapshot_file = snapshot_dir / f"{name}.json"
        artifact_file = artifact_dir / f"{name}.json"
        common.atomic_write_json(snapshot_file, {
            "schema_version": 1, "proposal": proposal,
            "identity": {key: context[key] for key in ("repository_id", "repository", "number", "head_sha", "base_ref")},
            "changed_paths": paths,
        })
        artifact = wait_for_artifact(snapshot_file, artifact_file)
    return docs_impact.evaluate(payload, delivery_id, token, artifact, paths=paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", default=os.environ.get("GC_GITHUB_EVENT_PAYLOAD_FILE", ""))
    parser.add_argument("--delivery-id", default=os.environ.get("GC_GITHUB_DELIVERY_ID", ""))
    parser.add_argument("--token-env", default="GH_TOKEN")
    args = parser.parse_args()
    if not args.payload_file:
        parser.error("--payload-file or GC_GITHUB_EVENT_PAYLOAD_FILE is required")
    token = os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"{args.token_env} is required")
    with open(args.payload_file, encoding="utf-8") as handle:
        payload = docs_impact.webhook_payload(json.load(handle))
    context = service.github_pr_context(payload)
    proposal_file = proposal_inbox_path(context)
    root = pathlib.Path(common.data_dir())
    print(json.dumps(run_handoff(
        payload, args.delivery_id, token, proposal_file,
        pathlib.Path(os.environ.get("GC_GITHUB_DOCS_PATCH_SNAPSHOT_DIR", root / "docs-patch-snapshots")),
        pathlib.Path(os.environ.get("GC_GITHUB_DOCS_PATCH_ARTIFACT_DIR", root / "docs-patch-artifacts")),
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
