#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

import github_intake_service as service


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GitHub App configuration from the configured identity resolver")
    parser.add_argument(
        "--identity",
        default="",
        help="GitHub App identity to resolve; defaults to GITHUB_INTAKE_APP_IDENTITY",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="emit raw JSON")
    parser.add_argument("--quiet", action="store_true", help="print only errors")
    args = parser.parse_args()

    try:
        outcome = service.sync_github_app_config_from_identity(args.identity)
    except Exception as exc:  # noqa: BLE001 - command boundary reports resolver/config errors.
        print(f"gc github sync-app: {exc}", file=sys.stderr)
        return 1
    if outcome.get("status") == "skipped":
        # The cooldown order is installed with the generic GitHub pack, while
        # identity-resolver onboarding is optional. Treat an absent identity as
        # a successful no-op so manually configured App deployments do not
        # emit a periodic controller failure. Resolver/configuration failures
        # still arrive through the exception path above.
        if args.quiet:
            return 0
        if args.json_output:
            print(json.dumps(outcome, indent=2, sort_keys=True))
            return 0
        print(f"status: skipped ({outcome.get('reason', 'sync skipped')})")
        return 0
    if args.quiet:
        return 0
    if args.json_output:
        print(json.dumps(outcome, indent=2, sort_keys=True))
        return 0
    print(f"status: {outcome.get('status')}")
    print(f"identity: {outcome.get('identity')}")
    app = (outcome.get("config") or {}).get("app") or {}
    print(f"app_id: {app.get('app_id', '(unset)')}")
    print(f"installation_id: {app.get('installation_id', '(unset)')}")
    print(f"slug: {app.get('slug', '(unset)')}")
    print(f"webhook_secret_present: {app.get('webhook_secret_present') is True}")
    print(f"private_key_pem_present: {app.get('private_key_pem_present') is True}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
