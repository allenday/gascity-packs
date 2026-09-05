#!/usr/bin/env python3
"""Run the locked durable documentation-journey controller operations."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import github_intake_common as common
from github_docs_journey import (
    FileJourneyStore,
    begin_journey,
    journey_request_matches,
    new_journey,
    project_configured_journey,
    record_child_update,
)


# One admitted child has three staged prerequisites (GitHub issue, Bead, and
# Bead assignment).  A second short sequence settles a returned worker update
# (PR, terminal reconciliation, terminal status).  This cap prevents an
# unhealthy adapter from turning one formula invocation into an unbounded
# retry loop; the persisted controller retains its own non-progress budget.
MAX_SETTLE_PASSES = 8


def _strict_json_object(value: str) -> dict[str, Any]:
    """Parse one JSON object, rejecting duplicate keys and non-object input."""
    try:
        parsed = json.loads(value, object_pairs_hook=_unique_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("--input must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--input must be a JSON object")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _only_fields(payload: dict[str, Any], fields: set[str]) -> None:
    unexpected = set(payload) - fields
    missing = fields - set(payload)
    if unexpected or missing:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if unexpected:
            details.append("unexpected " + ", ".join(sorted(unexpected)))
        raise ValueError("invalid command input: " + "; ".join(details))


def start_or_admit(state_dir: str, payload: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    """Durably create/adopt one exact journey, then admit one decision."""
    _only_fields(payload, {"request", "decision"})
    request = payload["request"]
    decision = payload["decision"]
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    identity = new_journey(request, now=0)["identity"]
    store = FileJourneyStore(state_dir)
    with store.lock(identity):
        existing = store.load(identity)
        if existing is not None and not journey_request_matches(existing, request):
            raise ValueError("journey request does not match the persisted journey")
        journey, action = begin_journey(request, decision, time.time() if now is None else now, existing_journey=existing)
        if journey is None:
            raise ValueError("journey admission was rejected")
        stored = store.save(journey)
    if action is None:
        admission = "sufficient"
    elif action.get("kind") == "create_issue":
        admission = "child-admitted"
    elif action.get("kind") in {"create_bud_issue", "create_debt_issue"} and action.get("bud_identity") is not None:
        admission = "bud-recorded"
    else:
        admission = "human-review-required"
    return {"journey": stored, "action": action, "admission": admission}


def record_update(state_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Durably accept one qualified worker update for an admitted child."""
    _only_fields(payload, {"identity", "update"})
    identity = payload["identity"]
    update = payload["update"]
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("identity must be non-empty text")
    if not isinstance(update, dict):
        raise ValueError("update must be an object")
    store = FileJourneyStore(state_dir)
    with store.lock(identity):
        journey = store.load(identity)
        if journey is None:
            raise ValueError("documentation journey was not found")
        updated, action = record_child_update(journey, update)
        stored = store.save(updated)
    return {"journey": stored, "action": action}


def activate_bud(state_dir: str, payload: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    """Start a fresh recursion from one recorded inert bud and new context."""
    _only_fields(payload, {"identity", "bud_identity", "context"})
    identity, bud_identity, context = payload["identity"], payload["bud_identity"], payload["context"]
    if not isinstance(identity, str) or not identity.strip() or not isinstance(bud_identity, str) or not bud_identity.strip():
        raise ValueError("identity and bud_identity must be non-empty text")
    if not isinstance(context, dict):
        raise ValueError("new context must be an object")
    store = FileJourneyStore(state_dir)
    with store.lock(identity):
        old = store.load(identity)
        if old is None:
            raise ValueError("documentation journey was not found")
        buds = old.get("buds", old.get("debts", []))
        bud = next((item for item in buds if isinstance(item, dict) and item.get("identity", item.get("key")) == bud_identity), None)
        if bud is None:
            raise ValueError("bud was not found")
        old_context = old.get("context", old.get("source"))
        if context == old_context:
            raise ValueError("new context must differ from the recorded bud context")
        if old.get("schema_version") != 3:
            raise ValueError("legacy buds are readable but cannot be activated without a normalized recursion context")
        request = {
            "repository_id": old["context"]["repository_id"], "repository": old["context"]["repository"],
            "installation_id": old["context"]["installation_id"], "context": context,
            "persona_goal_path": old["persona_goal_path"], "execution_budgets": old["execution_budgets"],
            "coverage_cells": [bud["decision_identity"]["coverage_cell"]],
        }
        fresh = new_journey(request, time.time() if now is None else now)
        fresh["activation"] = {"bud_identity": bud_identity, "coverage_cell": bud["decision_identity"]["coverage_cell"],
                               "parent_identity": old["identity"]}
        with store.lock(fresh["identity"]):
            if store.load(fresh["identity"]) is not None:
                raise ValueError("activated recursion already exists")
            stored = store.save(fresh)
    return {"journey": stored, "action": None}


def _pending_actions(journey: dict[str, Any]) -> list[dict[str, Any]]:
    actions = journey.get("actions")
    if not isinstance(actions, list):
        raise ValueError("documentation journey actions are invalid")
    return [action for action in actions if isinstance(action, dict) and action.get("state") == "pending"]


def _worker_ready_children(journey: dict[str, Any]) -> list[str]:
    """Return admitted children whose projected lifecycle prerequisites settled."""
    actions = journey.get("actions")
    children = journey.get("children")
    if not isinstance(actions, list) or not isinstance(children, list):
        raise ValueError("documentation journey is invalid")
    ready: list[str] = []
    required = {"create_issue", "create_bead", "assign_bead"}
    for child in children:
        if not isinstance(child, dict) or child.get("state") != "admitted":
            continue
        key = child.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("admitted child key is invalid")
        lifecycle = [
            action for action in actions
            if isinstance(action, dict) and action.get("child_key") == key and action.get("kind") in required
        ]
        # v3's ``create_bead`` action is a durable alias that adopts the
        # direct Bead created by its initial action; it never creates a
        # second City work item.
        if {str(action.get("kind")) for action in lifecycle} == required and all(action.get("state") == "completed" for action in lifecycle):
            ready.append(key)
    return ready


def _needs_terminal_reconciliation(journey: dict[str, Any]) -> bool:
    """Whether one more controller pass can stage a terminal status action."""
    if journey.get("state") != "active":
        return False
    children = journey.get("children")
    if not isinstance(children, list) or not children:
        return False
    complete = {"complete", "cancelled", "blocked", "failed"}
    return all(isinstance(child, dict) and child.get("state") in complete for child in children)


def project_until_settled(state_dir: str, identity: str, *, max_passes: int = MAX_SETTLE_PASSES) -> dict[str, Any]:
    """Project/reconcile a journey until it is safe to dispatch or terminally settled.

    The one-step ``project`` command remains the restart-compatible primitive.
    This operation is the formula-facing readiness boundary: it never reports
    success while an admitted child lacks its App issue, Bead, or assignment.
    """
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("identity must be non-empty text")
    if type(max_passes) is not int or max_passes <= 0:
        raise ValueError("max_passes must be a positive integer")
    last: dict[str, Any] | None = None
    for pass_number in range(1, max_passes + 1):
        journey = project_configured_journey(state_dir, identity)
        if not _pending_actions(journey) and not _needs_terminal_reconciliation(journey):
            return {
                "journey": journey,
                "settled": True,
                "passes": pass_number,
                "worker_ready_children": _worker_ready_children(journey),
            }
        last = journey
    pending = _pending_actions(last or {})
    raise RuntimeError(
        f"documentation journey did not settle within {max_passes} passes "
        f"({len(pending)} pending actions)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start-or-admit", "activate-bud", "project", "project-until-settled", "record-child-update"))
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--store", default=common.docs_review_runs_dir() + "-journeys")
    parser.add_argument("--identity")
    parser.add_argument("--input", help="strict JSON object for start-or-admit or record-child-update")
    args = parser.parse_args()
    try:
        if args.operation in {"project", "project-until-settled"}:
            if not args.identity or args.input is not None:
                raise ValueError(f"{args.operation} requires --identity and does not accept --input")
            result: Any = (
                project_configured_journey(args.store, args.identity)
                if args.operation == "project"
                else project_until_settled(args.store, args.identity)
            )
        else:
            if args.identity is not None or args.input is None:
                raise ValueError(f"{args.operation} requires --input and does not accept --identity")
            payload = _strict_json_object(args.input)
            if args.operation == "start-or-admit":
                result = start_or_admit(args.store, payload)
            elif args.operation == "activate-bud":
                result = activate_bud(args.store, payload)
            else:
                result = record_update(args.store, payload)
    except (OSError, ValueError, RuntimeError, common.GitHubAPIError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
