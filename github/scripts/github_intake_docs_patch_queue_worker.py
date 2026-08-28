#!/usr/bin/env python3
"""Consume sanitized TechDocs queue snapshots without network or credentials."""

from __future__ import annotations

import argparse
import os
import pathlib
import time

import github_intake_docs_patch_worker as worker


def consume_once(snapshot_dir: pathlib.Path, artifact_dir: pathlib.Path) -> int:
    """Canonically publish every queued snapshot not already represented by output."""
    worker.reject_credentials()
    artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handled = 0
    for snapshot_file in sorted(snapshot_dir.glob("*.json")):
        artifact_file = artifact_dir / snapshot_file.name
        if artifact_file.is_file():
            continue
        try:
            worker.write_artifact(artifact_file, worker.load_snapshot(snapshot_file))
            handled += 1
        except ValueError:
            # The trusted supervisor will turn absent/invalid output into its
            # human-friendly required-action result; never emit partial output.
            continue
    return handled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", default=os.environ.get("GC_TECHDOCS_SNAPSHOT_DIR", "/work/snapshot"))
    parser.add_argument("--artifact-dir", default=os.environ.get("GC_TECHDOCS_ARTIFACT_DIR", "/work/artifact"))
    parser.add_argument("--poll-seconds", type=float, default=0.2)
    args = parser.parse_args()
    snapshot_dir, artifact_dir = pathlib.Path(args.snapshot_dir), pathlib.Path(args.artifact_dir)
    while True:
        consume_once(snapshot_dir, artifact_dir)
        time.sleep(max(0.05, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
