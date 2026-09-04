#!/usr/bin/env python3
"""Admit one classified PR reviewer candidate into a persisted recursion."""

from __future__ import annotations

import argparse
import json
import sys

import github_intake_common as common
from github_intake_docs_direct_child_complete import admit_direct_child
from github_intake_docs_journey_commands import _strict_json_object


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--store", default=common.docs_review_runs_dir() + "-journeys")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(admit_direct_child(args.store, _strict_json_object(args.input)), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, RuntimeError, common.GitHubAPIError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
