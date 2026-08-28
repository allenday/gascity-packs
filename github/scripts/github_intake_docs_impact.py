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
import github_intake_docs_patch as docs_patch
import github_intake_service as service

CHECK_NAME = "Gas City / docs-impact"
DOCS_PREFIXES = ("docs/", "doc/", "documentation/")
NON_PRODUCT_PREFIXES = (".github/", "test/", "tests/", "fixtures/", "scripts/")
DOCS_FILENAMES = {"readme.md", "changelog.md", "contributing.md"}
MAX_CHECK_DIFF_BYTES = 60 * 1024


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


def patch_check_output(
    context: dict[str, str], source: dict[str, Any], artifact: dict[str, Any] | None, outcome: str, reason: str = "",
    paths: list[str] | None = None,
) -> dict[str, str]:
    """Render an actionable, bounded public projection of validated artifact data."""
    summary: list[str] = []
    if outcome == "proposed" and artifact is not None:
        digest = str(artifact["artifact_sha256"])
        summary.extend([
            "A documentation update was proposed for this pull request.",
            "",
            f"Artifact digest: `{digest}`",
            "",
            "Apply this documentation patch through the approved review workflow; this check does not write a branch or open a pull request.",
        ])
        diff = str(artifact["diff"])
        encoded = diff.encode("utf-8")
        if len(encoded) > MAX_CHECK_DIFF_BYTES:
            diff = encoded[:MAX_CHECK_DIFF_BYTES].decode("utf-8", errors="ignore").rstrip() + "\n…"
        return {"title": "Documentation update proposed", "summary": "\n".join(summary), "text": f"```diff\n{diff}\n```"}
    classification, explanation = classify_paths(paths or [])
    display_paths = ", ".join(f"`{path}`" for path in (paths or [])[:8]) or "no changed files"
    if classification == "no-impact":
        return {
            "title": "No documentation update needed",
            "summary": f"This revision changes {display_paths}. {explanation}",
        }
    task = (
        "Update the developer documentation that explains the changed behavior, then push the documentation commit to this pull request."
        if classification == "needs-human-decision"
        else "Review the documentation already changed with this revision, or add the missing developer guidance, then push a new commit."
    )
    summary.extend([
        f"This revision changes {display_paths}.",
        explanation,
        "",
        f"Next step: {task}",
    ])
    safe_reasons = {
        "artifact_unavailable": "No documentation patch artifact was supplied.",
        "artifact_invalid": "The documentation patch artifact failed validation.",
        "artifact_identity_mismatch": "The proposal is bound to a different pull request revision.",
        "artifact_persistence_failed": "The validated documentation patch artifact could not be persisted.",
        "unavailable": "The documentation proposal is unavailable.",
        "unsafe": "The documentation proposal was marked unsafe.",
    }
    if reason not in {"artifact_unavailable", ""}:
        summary.extend(["", safe_reasons.get(reason, "The documentation proposal was unavailable or unsafe.")])
    return {"title": "Documentation review needed", "summary": "\n".join(summary)}


def artifact_matches_context(artifact: dict[str, Any], context: dict[str, str]) -> bool:
    identity = artifact["identity"]
    return (
        identity["repository_id"] == context["repository_id"]
        and identity["repository"] == context["repository"]
        and str(identity["pr_number"]) == context["number"]
        and identity["head_sha"] == context["head_sha"]
    )


def project_docs_patch(context: dict[str, str], source: dict[str, Any], proposal: dict[str, Any] | None) -> dict[str, Any]:
    """Validate then persist a derived result; an invalid result never inherits a source SHA."""
    if proposal is None:
        return {"outcome": "unavailable", "reason": "artifact_unavailable", "artifact": None, "result": None}
    try:
        artifact = docs_patch.validate_artifact(proposal)
    except ValueError:
        return {"outcome": "unavailable", "reason": "artifact_invalid", "artifact": None, "result": None}
    if not artifact_matches_context(artifact, context):
        return {"outcome": "unavailable", "reason": "artifact_identity_mismatch", "artifact": None, "result": None}
    result = service.create_pull_request_docs_patch_result(context, source, artifact)
    if result.get("status") not in {"created", "duplicate"}:
        return {"outcome": "unavailable", "reason": "artifact_persistence_failed", "artifact": None, "result": result}
    outcome = "proposed" if artifact["status"] == "proposed" else "unavailable"
    return {"outcome": outcome, "reason": str(artifact["status"]), "artifact": artifact, "result": result}


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
    paths = paths or []
    run_url = common.docs_impact_run_url(context["repository"], context["repository_id"], context["number"], context["head_sha"])
    service.save_docs_impact_run(context, source, None, "evaluating", "", paths, None)
    initial = common.create_check_run_with_token(
        token, context["owner"], context["repo"], context["head_sha"], CHECK_NAME, "in_progress", None,
        check_output("Evaluating docs impact", "Gas City is evaluating this revision.", context, source, []), run_url,
    )
    check_id = initial.get("id")
    if not check_id:
        raise RuntimeError("GitHub did not return a check run id")
    projection = project_docs_patch(context, source, artifact)
    classification, _ = classify_paths(paths)
    outcome = projection["outcome"] if projection["outcome"] == "proposed" else classification
    service.save_docs_impact_run(context, source, projection["artifact"], outcome, projection["reason"], paths, initial)
    completed = common.update_check_run_with_token(
        token, context["owner"], context["repo"], check_id, "completed", conclusion_for(outcome),
        patch_check_output(context, source, projection["artifact"], outcome, projection["reason"], paths),
    )
    return {"outcome": outcome, "reason": projection["reason"], "source": source,
            "result": projection["result"], "check_run": completed, "head_sha": context["head_sha"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", default=os.environ.get("GC_GITHUB_EVENT_PAYLOAD_FILE", ""))
    parser.add_argument("--delivery-id", default=os.environ.get("GC_GITHUB_DELIVERY_ID", ""))
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument("--artifact-file", default=os.environ.get("GC_GITHUB_DOCS_PATCH_ARTIFACT_FILE", ""))
    args = parser.parse_args()
    if not args.payload_file:
        parser.error("--payload-file or GC_GITHUB_EVENT_PAYLOAD_FILE is required")
    token = os.environ.get(args.token_env, "")
    if not token:
        parser.error(f"{args.token_env} is required")
    with open(args.payload_file, encoding="utf-8") as handle:
        payload = webhook_payload(json.load(handle))
    artifact = None
    if args.artifact_file:
        try:
            with open(args.artifact_file, encoding="utf-8") as handle:
                loaded = json.load(handle)
            artifact = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            artifact = None
    result = evaluate(payload, args.delivery_id, token, artifact)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
