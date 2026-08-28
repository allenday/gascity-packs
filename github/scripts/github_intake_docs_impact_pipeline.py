#!/usr/bin/env python3
"""Queue one PR revision and publish only its exact completed TechDocs review.

This trusted command runs with a short-lived GitHub installation token. It
queues the sanitized assignment consumed by the isolated worker, waits for the
matching outbox envelope, independently validates the exact assignment bytes
and candidate binding, then delegates projection and publication to the
idempotent docs-impact boundary. Missing or invalid output creates no check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any, Callable

import github_intake_common as common
import github_intake_docs_impact as docs_impact
import github_intake_docs_patch as docs_patch
import github_intake_docs_patch_worker as patch_worker
import github_intake_service as service

QUEUE_ARTIFACT_SCHEMA_VERSION = 1


def changed_paths(token: str, context: dict[str, str]) -> list[str]:
    files = common.list_pull_request_files_with_token(
        token, context["owner"], context["repo"], context["number"],
    )
    paths = [str(file.get("filename", "")).strip() for file in files]
    return sorted({path for path in paths if path})


def validate_review_candidate(raw_assignment: bytes, value: Any) -> dict[str, Any] | None:
    """Validate one outbox envelope against precisely the assignment bytes read."""
    try:
        assignment = patch_worker.load_assignment_bytes(raw_assignment)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "snapshot_sha256", "artifact"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != QUEUE_ARTIFACT_SCHEMA_VERSION
            or value["snapshot_sha256"] != hashlib.sha256(raw_assignment).hexdigest()
            or not isinstance(value["artifact"], dict)
        ):
            return None
        review = docs_patch.validate_agent_review(value["artifact"])
    except (KeyError, TypeError, ValueError):
        return None
    if review["identity"] != assignment["identity"] or review["agent_skill"] != assignment["agent_skill"]:
        return None
    return review


def load_review_candidate(
    assignment_file: pathlib.Path, artifact_file: pathlib.Path,
) -> dict[str, Any] | None:
    """Read both trust-boundary files and return only their exact valid review."""
    try:
        raw_assignment = assignment_file.read_bytes()
        envelope = json.loads(artifact_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return validate_review_candidate(raw_assignment, envelope)


def wait_for_sidecar_review(
    assignment_file: pathlib.Path, artifact_file: pathlib.Path, wait_seconds: float,
) -> dict[str, Any] | None:
    """Wait a bounded interval for the exact revision-bound review candidate."""
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        review = load_review_candidate(assignment_file, artifact_file)
        if review is not None:
            return review
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def configured_wait_seconds() -> float:
    raw = os.environ.get(
        "GC_GITHUB_DOCS_REVIEW_WAIT_SECONDS",
        os.environ.get("GC_GITHUB_DOCS_PATCH_WAIT_SECONDS", "15"),
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def run_handoff(
    payload: dict[str, Any],
    delivery_id: str,
    token: str,
    snapshot_dir: pathlib.Path,
    artifact_dir: pathlib.Path,
    wait_for_review: Callable[[pathlib.Path, pathlib.Path, float], dict[str, Any] | None] = wait_for_sidecar_review,
    *,
    wait_seconds: float | None = None,
) -> dict[str, Any]:
    """Queue, consume, project, and publish one immutable PR revision."""
    context = service.github_pr_context(payload)
    paths = changed_paths(token, context)
    queued = docs_impact.evaluate(payload, delivery_id, token, paths=paths)
    try:
        assignment_file = pathlib.Path(str(queued["assignment_path"]))
        source = queued["source"]
    except (KeyError, TypeError):
        return {"status": "queued", "reason": "assignment_result_invalid", "head_sha": context["head_sha"]}
    if (
        not isinstance(source, dict)
        or assignment_file.suffix != ".json"
        or assignment_file.parent.resolve() != snapshot_dir.resolve()
    ):
        return {"status": "queued", "reason": "assignment_path_invalid", "head_sha": context["head_sha"]}
    artifact_file = artifact_dir / assignment_file.name
    review = wait_for_review(
        assignment_file,
        artifact_file,
        configured_wait_seconds() if wait_seconds is None else max(0.0, wait_seconds),
    )
    if review is None:
        return queued
    record = docs_impact.project_agent_review(context, source, review)
    if record is None:
        return {"status": "candidate_rejected", "head_sha": context["head_sha"]}
    return docs_impact.publish_agent_review(token, context, review)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", default=os.environ.get("GC_GITHUB_EVENT_PAYLOAD_FILE", ""))
    parser.add_argument("--delivery-id", default=os.environ.get("GC_GITHUB_DELIVERY_ID", ""))
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument("--wait-seconds", type=float, default=configured_wait_seconds())
    args = parser.parse_args()
    if not args.payload_file:
        parser.error("--payload-file or GC_GITHUB_EVENT_PAYLOAD_FILE is required")
    token = os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"{args.token_env} is required")
    with open(args.payload_file, encoding="utf-8") as handle:
        payload = docs_impact.webhook_payload(json.load(handle))
    root = pathlib.Path(common.data_dir())
    print(json.dumps(run_handoff(
        payload,
        args.delivery_id,
        token,
        pathlib.Path(os.environ.get("GC_GITHUB_DOCS_PATCH_SNAPSHOT_DIR", root / "docs-patch-snapshots")),
        pathlib.Path(os.environ.get("GC_GITHUB_DOCS_PATCH_ARTIFACT_DIR", root / "docs-patch-artifacts")),
        wait_seconds=args.wait_seconds,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
