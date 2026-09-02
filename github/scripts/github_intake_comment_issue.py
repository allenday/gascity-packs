#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

import github_intake_common as common


def load_profile_github_app(identity: str) -> dict[str, str]:
    import github_intake_service as service

    return service.load_profile_github_app(identity)


def app_config(identity: str) -> dict[str, object]:
    identity = common.validate_github_app_identity(identity)
    if identity:
        return load_profile_github_app(identity)
    config = common.load_effective_config()
    app_cfg = config.get("app", {})
    if isinstance(app_cfg, dict):
        return app_cfg
    return {}


def split_repository(value: str) -> tuple[str, str]:
    owner, sep, repo = value.strip().partition("/")
    if not owner or not sep or not repo:
        raise SystemExit("repository must be in owner/repo format")
    return owner, repo


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as handle:
            return handle.read()
    if args.body_stdin:
        return sys.stdin.read()
    return args.body


def main() -> int:
    parser = argparse.ArgumentParser(description="Post an issue comment via the workspace GitHub App")
    parser.add_argument("repository", help="owner/repo")
    parser.add_argument("issue_number", help="GitHub issue number")
    parser.add_argument("--installation-id", default="", help="GitHub App installation id")
    parser.add_argument(
        "--github-app-identity",
        default="",
        help="GitHub App identity that should post the comment",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", default="", help="comment markdown")
    group.add_argument("--body-file", default="", help="path to a markdown file")
    group.add_argument("--body-stdin", action="store_true", help="read comment markdown from standard input")
    args = parser.parse_args()

    try:
        app_cfg = app_config(args.github_app_identity)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not isinstance(app_cfg, dict) or not app_cfg.get("app_id") or not app_cfg.get("private_key_pem"):
        raise SystemExit("GitHub App configuration is incomplete")
    installation_id = str(args.installation_id or app_cfg.get("installation_id", "")).strip()
    if not installation_id:
        raise SystemExit("GitHub App installation id is required")
    owner, repo = split_repository(args.repository)
    comment = common.post_issue_comment(
        app_cfg,
        installation_id,
        owner,
        repo,
        args.issue_number,
        read_body(args),
    )
    print(json.dumps(comment, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
