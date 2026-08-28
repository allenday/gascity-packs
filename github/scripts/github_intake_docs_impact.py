#!/usr/bin/env python3
"""Evaluate one immutable GitHub pull-request revision for documentation impact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import github_intake_service as service

def create_source(payload: dict[str, Any], delivery_id: str, context: dict[str, str]) -> dict[str, Any]:
    source_key = service.github_pr_source_key(context)
    request = {
        "source_key": source_key,
        "repository_full_name": context["repository"],
        "repository_id": context["repository_id"],
        "pr_number": context["number"],
        "pr_url": context["url"],
        "head_sha": context["head_sha"],
        "installation_id": str((payload.get("installation") or {}).get("id", "")),
        "delivery_id": delivery_id,
        "raw_payload_path": os.environ.get("GC_GITHUB_EVENT_PAYLOAD_FILE", ""),
    }
    return service.create_pull_request_source(request)


def webhook_payload(document: dict[str, Any]) -> dict[str, Any]:
    """Accept either a direct webhook payload or the durable intake envelope."""
    nested = document.get("payload")
    if isinstance(nested, dict):
        return nested
    return document


def evaluate(
    payload: dict[str, Any], delivery_id: str, token: str, artifact: dict[str, Any] | None = None,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    context = service.github_pr_context(payload)
    source = create_source(payload, delivery_id, context)
    if source.get("status") not in {"created", "duplicate"}:
        raise RuntimeError(f"could not create source bead: {source.get('reason', source.get('status'))}")
    queue = service.queue_agent_review(context, source, paths or [])
    if queue.get("status") not in {"queued", "duplicate"}:
        raise RuntimeError(f"could not queue agent review: {queue.get('reason', queue.get('status'))}")
    return {"status": "queued", "source": source, "assignment": queue["assignment"],
            "assignment_path": queue["assignment_path"], "head_sha": context["head_sha"]}


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
        payload = webhook_payload(json.load(handle))
    result = evaluate(payload, args.delivery_id, token)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
