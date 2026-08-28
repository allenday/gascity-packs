#!/usr/bin/env python3
"""Evaluate one immutable GitHub pull-request revision for documentation impact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import github_intake_docs_patch as docs_patch
import github_intake_service as service


SUCCESSFUL_REVIEW_VERDICTS = {"no-impact", "docs-sufficient"}


def _review_identity(context: dict[str, str]) -> dict[str, Any] | None:
    """Return the one agent-review identity a PR revision may authorize."""
    try:
        number = int(context["number"])
        identity = {
            "repository_id": context["repository_id"],
            "repository": context["repository"],
            "pr_number": number,
            "head_sha": context["head_sha"],
            "source_key": service.github_pr_source_key(context),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return identity if number > 0 else None


def project_agent_review(
    context: dict[str, str], source: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any] | None:
    """Persist only a canonical review bound to this exact source revision."""
    expected_identity = _review_identity(context)
    if expected_identity is None or not isinstance(source, dict):
        return None
    try:
        validated = docs_patch.validate_agent_review(review)
    except (TypeError, ValueError):
        return None
    if validated["identity"] != expected_identity:
        return None
    if str(source.get("source_key", "")).strip() != expected_identity["source_key"]:
        return None
    with service.docs_impact_run_lock(context):
        return service.save_agent_review_run(context, validated)


def publish_agent_review(token: str, context: dict[str, str], review: dict[str, Any]) -> dict[str, Any]:
    """Create the sole terminal Check Run after its exact review was persisted."""
    expected_identity = _review_identity(context)
    if expected_identity is None:
        return {"status": "ignored", "reason": "context_invalid"}
    try:
        validated = docs_patch.validate_agent_review(review)
    except (TypeError, ValueError):
        return {"status": "ignored", "reason": "review_invalid"}
    if validated["identity"] != expected_identity:
        return {"status": "ignored", "reason": "review_identity_mismatch"}
    with service.docs_impact_run_lock(context):
        record = service.load_docs_impact_run(context)
        if not isinstance(record, dict) or record.get("review") != validated:
            return {"status": "ignored", "reason": "review_not_projected"}
        if str(record.get("check_run_id", "")).strip():
            return {"status": "duplicate", "check_run_id": str(record["check_run_id"])}
        if record.get("publication_state") != "ready":
            return {"status": "publication_pending"}
        try:
            owner, repository = context["repository"].split("/", 1)
        except (KeyError, ValueError):
            return {"status": "ignored", "reason": "repository_invalid"}
        record = service.begin_agent_review_publication(context, validated)
        if not isinstance(record, dict):
            return {"status": "ignored", "reason": "review_not_projected"}
        if record.get("publication_state") != "started":
            return {"status": "publication_pending"}
        public = record.get("public") if isinstance(record.get("public"), dict) else {}
        verdict = str(public.get("decision", ""))
        check_run = service.common.create_check_run_with_token(
            token,
            owner,
            repository,
            context["head_sha"],
            f"Documentation impact: {verdict}",
            "completed",
            "success" if verdict in SUCCESSFUL_REVIEW_VERDICTS else "action_required",
            {
                "title": f"Documentation impact: {verdict}",
                "summary": f"{public.get('why', '')}\n\nNext action: {public.get('next_action', '')}",
            },
            service.common.docs_impact_run_url(str(record.get("run_locator", ""))),
        )
        saved = service.complete_agent_review_publication(context, validated, check_run)
        if saved is None:
            return {"status": "publication_pending"}
        return {"status": "published", "check_run": check_run, "record": saved}

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
