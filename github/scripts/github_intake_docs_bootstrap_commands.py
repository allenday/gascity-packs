#!/usr/bin/env python3
"""Compatibility launcher for the former docs-bootstrap command."""

import argparse
import json

import github_intake_common as common
from github_docs_journey import project_configured_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("project",))
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--store", default=common.docs_review_runs_dir() + "-bootstrap")
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    try:
        root = project_configured_root(args.store, args.identity)
    except (OSError, ValueError, RuntimeError, common.GitHubAPIError) as exc:
        parser.error(str(exc))
    print(json.dumps(root, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
