#!/usr/bin/env python3
"""Complete one Pack-admitted v3 direct documentation child."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import time
from typing import Any

import github_intake_common as common
import github_intake_docs_patch_worker as review_worker
from github_docs_journey import FileJourneyStore, begin_journey, new_journey, record_child_update
from github_intake_docs_journey_commands import _strict_json_object


DIRECT_UPDATE_KIND = "github-docs-recursion-direct-child-update"
DIRECT_ADMISSION_KIND = "github-docs-recursion-direct-admission"
DIRECT_CONTEXT_FIELDS = {
    "repository_id", "repository", "pr_number", "source_key", "reviewed_head_sha",
    "source_branch", "source_url", "installation_id",
}
DIRECT_BUDGETS = {
    "max_depth": 1,
    "max_children": 1,
    "max_docs_prs": 1,
    "max_elapsed_seconds": 24 * 60 * 60,
    "max_non_progress": 3,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _direct_context(value: Any, assignment: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != DIRECT_CONTEXT_FIELDS:
        raise ValueError("direct admission context must contain only the signed PR fields")
    identity = assignment["identity"]
    duplicates = {
        "repository_id": identity["repository_id"],
        "repository": identity["repository"],
        "pr_number": identity["pr_number"],
        "source_key": identity["source_key"],
        "reviewed_head_sha": identity["head_sha"],
    }
    if any(value.get(field) != expected for field, expected in duplicates.items()):
        raise ValueError("direct admission context does not match the candidate assignment")
    expected_url = f"https://github.com/{identity['repository']}/pull/{identity['pr_number']}"
    if value.get("source_url") != expected_url:
        raise ValueError("direct admission context source_url does not match the candidate assignment")
    installation_id, source_branch = value.get("installation_id"), value.get("source_branch")
    if not isinstance(installation_id, str) or not installation_id or installation_id.strip() != installation_id:
        raise ValueError("direct admission context installation_id must be canonical text")
    if not isinstance(source_branch, str) or not source_branch or source_branch.strip() != source_branch:
        raise ValueError("direct admission context source_branch must be canonical text")
    candidate_identity = candidate["artifact"]["identity"]
    if candidate_identity != identity:
        raise ValueError("direct admission context does not match the classified candidate")
    return dict(value)


def _admission_response(identity: str, child: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": DIRECT_ADMISSION_KIND,
        "recursion_identity": identity,
        "admitted_child": copy.deepcopy(child),
    }


def admit_direct_child(state_dir: str, payload: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    """Persist and return one Pack-issued direct-child admission."""
    if not isinstance(payload, dict) or set(payload) != {"assignment_bytes", "candidate", "context"}:
        raise ValueError("direct admission requires assignment_bytes, candidate, and context")
    encoded = payload.get("assignment_bytes")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("direct admission assignment_bytes must be base64 text")
    try:
        raw_assignment = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("direct admission assignment_bytes must be valid base64") from exc
    candidate = review_worker.validate_direct_admission_candidate(raw_assignment, payload.get("candidate"))
    assignment = review_worker.load_assignment_bytes(raw_assignment)
    context = _direct_context(payload.get("context"), assignment, candidate)
    assignment_digest = hashlib.sha256(raw_assignment).hexdigest()
    candidate_digest = hashlib.sha256(_canonical_json(candidate).encode("utf-8")).hexdigest()
    request = {
        "repository_id": context["repository_id"],
        "repository": context["repository"],
        "installation_id": context["installation_id"],
        "context": {
            "kind": "github-pr", "key": context["source_key"], "url": context["source_url"],
            "repository_id": context["repository_id"], "repository": context["repository"],
            "installation_id": context["installation_id"], "docs_impact_source_key": context["source_key"],
            "default_branch": context["source_branch"], "default_branch_sha": context["reviewed_head_sha"],
            "projection_capabilities": [], "pr_number": context["pr_number"],
            "source_branch": context["source_branch"], "assignment_sha256": assignment_digest,
            "candidate_sha256": candidate_digest,
        },
        "persona_goal_path": candidate["persona_goal_path"],
        "coverage_cells": [cell["identity"] for cell in candidate["coverage_cells"]],
        "execution_budgets": DIRECT_BUDGETS,
    }
    decision = {
        "artifact": candidate["artifact"],
        "journey_disposition": "blocking",
        "coverage_cells": candidate["coverage_cells"],
    }
    expected_binding = {
        "assignment_sha256": assignment_digest,
        "candidate_sha256": candidate_digest,
        "context": copy.deepcopy(context),
    }
    identity = new_journey(request, now=0)["identity"]
    store = FileJourneyStore(state_dir)
    with store.lock(identity):
        existing = store.load(identity)
        if existing is not None:
            recorded_admission = existing.get("direct_admission")
            if (not isinstance(recorded_admission, dict)
                    or any(recorded_admission.get(key) != value for key, value in expected_binding.items())):
                raise ValueError("candidate does not match the persisted direct admission")
            admitted_child = recorded_admission.get("admitted_child")
            if not isinstance(admitted_child, dict):
                raise ValueError("persisted direct admission has no exact admitted child")
            return _admission_response(identity, admitted_child)
        journey, action = begin_journey(request, decision, time.time() if now is None else now)
        if (journey is None or journey.get("state") != "active" or not isinstance(journey.get("children"), list)
                or len(journey["children"]) != 1 or not isinstance(action, dict)):
            raise ValueError("classified candidate did not admit exactly one direct child")
        journey["direct_admission"] = {**expected_binding, "admitted_child": copy.deepcopy(journey["children"][0])}
        stored = store.save(journey)
    return _admission_response(identity, stored["children"][0])


def _validate_admission(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "kind", "recursion_identity", "admitted_child"}
            or value.get("schema_version") != 1 or value.get("kind") != DIRECT_ADMISSION_KIND
            or not isinstance(value.get("recursion_identity"), str) or not value["recursion_identity"]
            or not isinstance(value.get("admitted_child"), dict)):
        raise ValueError("completion requires the exact Pack-issued admission record")
    return value


def _validate_direct_update(value: Any, admitted_child: dict[str, Any]) -> dict[str, Any]:
    fields = {"schema_version", "kind", "admitted_child", "state", "documentation_branch"}
    if (not isinstance(value, dict) or set(value) != fields or value.get("schema_version") != 1
            or value.get("kind") != DIRECT_UPDATE_KIND or value.get("admitted_child") != admitted_child
            or value.get("state") not in {"complete", "blocked", "failed", "cancelled"}):
        raise ValueError("direct child update must echo the complete admitted child")
    return value


def complete_direct_child(state_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist one direct-child result, then stage its App PR."""
    if set(payload) == {"admission", "update"}:
        admission = _validate_admission(payload["admission"])
        update = _validate_direct_update(payload["update"], admission["admitted_child"])
        identity = admission["recursion_identity"]
        store = FileJourneyStore(state_dir)
        with store.lock(identity):
            journey = store.load(identity)
            if journey is None or journey.get("schema_version") != 3 or not isinstance(journey.get("direct_admission"), dict):
                raise ValueError("direct admission was not found")
            binding = journey["direct_admission"]
            if binding.get("admitted_child") != admission["admitted_child"]:
                raise ValueError("completion admission does not match the persisted direct child")
            child = next((item for item in journey["children"] if item.get("identity") == admission["admitted_child"].get("identity")), None)
            if child is None:
                raise ValueError("completion admission does not match the persisted direct child")
            recorded = child.get("direct_completion")
            if recorded is not None:
                if recorded != update:
                    raise ValueError("direct child completion conflicts with the persisted result")
                action = next((item for item in journey["actions"] if item.get("child_key") == child.get("key") and item.get("kind") == "create_docs_pr"), None)
                return {"journey": journey, "action": copy.deepcopy(action)}
            forwarded = copy.deepcopy(update)
            forwarded["kind"] = "github-docs-recursion-child-update"
            updated, action = record_child_update(journey, forwarded)
            updated_child = next((item for item in updated["children"] if item.get("identity") == child.get("identity")), None)
            if updated_child is None or updated_child.get("state") != update["state"]:
                raise ValueError("direct child update has invalid branch evidence")
            updated_child["direct_completion"] = copy.deepcopy(update)
            stored = store.save(updated)
        return {"journey": stored, "action": action}
    raise ValueError("direct completion requires the exact Pack-issued admission and update")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--store", default=common.docs_review_runs_dir() + "-journeys")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(complete_direct_child(args.store, _strict_json_object(args.input)), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, RuntimeError, common.GitHubAPIError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
