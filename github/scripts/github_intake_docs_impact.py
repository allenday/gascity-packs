#!/usr/bin/env python3
"""Evaluate one immutable GitHub pull-request revision for documentation impact."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

import github_intake_common as common
import github_intake_service as service

CHECK_NAME = "Gas City / docs-impact"
DOCS_PREFIXES = ("docs/", "doc/", "documentation/")
NON_PRODUCT_PREFIXES = (".github/", "test/", "tests/", "fixtures/", "scripts/")
DOCS_FILENAMES = {"readme.md", "changelog.md", "contributing.md"}


def classify_paths(paths: list[str]) -> tuple[str, str]:
    normalized = [path.strip().lower() for path in paths if path.strip()]
    if not normalized:
        return "needs-human-decision", "GitHub reported no changed paths; impact cannot be determined."
    documentation = [
        path for path in normalized if path.startswith(DOCS_PREFIXES) or pathlib.PurePosixPath(path).name in DOCS_FILENAMES
    ]
    product = [
        path for path in normalized if not path.startswith(DOCS_PREFIXES) and not path.startswith(NON_PRODUCT_PREFIXES)
        and pathlib.PurePosixPath(path).name not in DOCS_FILENAMES
    ]
    if product and documentation:
        return "docs-update-proposed", "Product and documentation paths changed together; review the proposed docs update."
    if product:
        return "needs-human-decision", "Product paths changed without documentation evidence."
    return "no-impact", "Only documentation, test, workflow, fixture, or automation paths changed."


def conclusion_for(outcome: str) -> str:
    return "success" if outcome == "no-impact" else "action_required"


def check_output(title: str, summary: str, context: dict[str, str], source: dict[str, Any], paths: list[str]) -> dict[str, str]:
    bead_id = str(source.get("bead_id", "unavailable"))
    rendered_paths = "\n".join(f"- `{path}`" for path in paths[:100]) or "- (none)"
    return {
        "title": title,
        "summary": "\n".join(
            [
                summary,
                "",
                f"Source bead: `{bead_id}`",
                f"Source key: `{service.github_pr_source_key(context)}`",
                f"Head SHA: `{context['head_sha']}`",
                "",
                "Changed paths:",
                rendered_paths,
            ]
        ),
    }


def create_source(payload: dict[str, Any], delivery_id: str, context: dict[str, str]) -> dict[str, Any]:
    source_key = service.github_pr_source_key(context)
    request = {
        "source_key": source_key,
        "repository_full_name": context["repository"],
        "repository_id": context["repository_id"],
        "item_kind": "pull-request",
        "item_number": context["number"],
        "item_url": context["url"],
        "installation_id": str((payload.get("installation") or {}).get("id", "")),
        "delivery_id": delivery_id,
        "raw_payload_path": os.environ.get("GC_GITHUB_EVENT_PAYLOAD_FILE", ""),
        "address": "docs-impact",
        "cleaned_body": "Evaluate this immutable pull-request revision for documentation impact.",
    }
    return service.create_addressed_source(request)


def evaluate(payload: dict[str, Any], delivery_id: str, token: str) -> dict[str, Any]:
    context = service.github_pr_context(payload)
    source = create_source(payload, delivery_id, context)
    if source.get("status") not in {"created", "duplicate"}:
        raise RuntimeError(f"could not create source bead: {source.get('reason', source.get('status'))}")
    initial = common.create_check_run_with_token(
        token, context["owner"], context["repo"], context["head_sha"], CHECK_NAME, "in_progress", None,
        check_output("Evaluating docs impact", "Gas City is evaluating this revision.", context, source, []),
    )
    check_id = initial.get("id")
    if not check_id:
        raise RuntimeError("GitHub did not return a check run id")
    files = common.list_pull_request_files_with_token(token, context["owner"], context["repo"], context["number"])
    paths = [str(item.get("filename", "")) for item in files]
    if len(files) >= 100:
        outcome, summary = "needs-human-decision", "Pull request has 100 or more changed files; impact requires review."
    else:
        outcome, summary = classify_paths(paths)
    completed = common.update_check_run_with_token(
        token, context["owner"], context["repo"], check_id, "completed", conclusion_for(outcome),
        check_output(outcome, summary, context, source, paths),
    )
    return {"outcome": outcome, "source": source, "check_run": completed, "head_sha": context["head_sha"]}


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
        payload = json.load(handle)
    result = evaluate(payload, args.delivery_id, token)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
