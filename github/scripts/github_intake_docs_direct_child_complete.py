#!/usr/bin/env python3
"""Complete one v3 direct documentation child through the Pack controller."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from typing import Any

import github_intake_common as common
from github_intake_docs_journey_commands import _strict_json_object, record_update


DIRECT_UPDATE_KIND = "github-docs-recursion-direct-child-update"


def complete_direct_child(state_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist one direct-child result, then stage its App PR."""
    if set(payload) != {"identity", "update"} or not isinstance(payload["identity"], str) or not payload["identity"].strip():
        raise ValueError("direct child completion requires identity and update")
    update = payload["update"]
    if not isinstance(update, dict) or update.get("schema_version") != 1 or update.get("kind") != DIRECT_UPDATE_KIND:
        raise ValueError("direct child update kind is invalid")
    forwarded = copy.deepcopy(update)
    forwarded["kind"] = "github-docs-recursion-child-update"
    result = record_update(state_dir, {"identity": payload["identity"], "update": forwarded})
    if result["action"] is None and result["journey"].get("children"):
        raise ValueError("direct child update did not match an admitted child or valid branch evidence")
    return result


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
