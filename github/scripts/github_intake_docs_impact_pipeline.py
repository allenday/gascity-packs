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
import subprocess
import sys
from typing import Any, Callable

import github_intake_common as common
import github_intake_docs_impact as docs_impact
import github_intake_service as service


def tokenless_worker_env(parent: dict[str, str] | None = None) -> dict[str, str]:
    """Return the minimal child environment, explicitly excluding credentials."""
    parent = parent or os.environ
    allowed = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TZ")
    return {name: parent[name] for name in allowed if parent.get(name)}


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


def worker_command(snapshot_file: pathlib.Path, artifact_file: pathlib.Path) -> None:
    worker = pathlib.Path(__file__).with_name("github_intake_docs_patch_worker.py")
    result = subprocess.run(
        [sys.executable, str(worker), "--snapshot-file", str(snapshot_file), "--artifact-file", str(artifact_file)],
        text=True, capture_output=True, env=tokenless_worker_env(), check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tokenless TechDocs worker failed: {result.stderr.strip() or result.stdout.strip()}")


def run_handoff(
    payload: dict[str, Any], delivery_id: str, token: str, proposal_file: pathlib.Path | None,
    work_root: pathlib.Path, run_worker: Callable[[pathlib.Path, pathlib.Path], None] = worker_command,
) -> dict[str, Any]:
    """Create the safe worker handoff and project its artifact for this exact SHA."""
    context = service.github_pr_context(payload)
    paths = changed_paths(token, context)
    proposal = read_proposal(proposal_file)
    artifact: dict[str, Any] | None = None
    if proposal is not None:
        work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        snapshot_file = work_root / "snapshot.json"
        artifact_file = work_root / "artifact.json"
        common.atomic_write_json(snapshot_file, {
            "schema_version": 1, "proposal": proposal,
            "identity": {key: context[key] for key in ("repository_id", "repository", "number", "head_sha", "base_ref")},
            "changed_paths": paths,
        })
        try:
            run_worker(snapshot_file, artifact_file)
            produced = common.read_json(artifact_file, None)
            artifact = produced if isinstance(produced, dict) else None
        except (OSError, RuntimeError):
            artifact = None
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
    work_root = pathlib.Path(common.data_dir()) / "docs-patch-handoffs" / common.safe_storage_id(service.github_pr_source_key(context), "handoff")
    print(json.dumps(run_handoff(payload, args.delivery_id, token, proposal_file, work_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
