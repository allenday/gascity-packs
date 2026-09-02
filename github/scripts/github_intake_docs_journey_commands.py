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
    return {"journey": stored, "action": action}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("start-or-admit", "project", "record-child-update"))
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--store", default=common.docs_review_runs_dir() + "-journeys")
    parser.add_argument("--identity")
    parser.add_argument("--input", help="strict JSON object for start-or-admit or record-child-update")
    args = parser.parse_args()
    try:
        if args.operation == "project":
            if not args.identity or args.input is not None:
                raise ValueError("project requires --identity and does not accept --input")
            result: Any = project_configured_journey(args.store, args.identity)
        else:
            if args.identity is not None or args.input is None:
                raise ValueError(f"{args.operation} requires --input and does not accept --identity")
            payload = _strict_json_object(args.input)
            if args.operation == "start-or-admit":
                result = start_or_admit(args.store, payload)
            else:
                result = record_update(args.store, payload)
    except (OSError, ValueError, RuntimeError, common.GitHubAPIError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
