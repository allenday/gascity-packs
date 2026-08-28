#!/usr/bin/env python3
"""Run the no-tools cagent TechDocs reviewer and emit one bound review.

This program is deliberately suitable only for the egress sidecar.  It has no
GitHub client and receives neither a checkout nor GitHub credentials; identity
and immutable evidence references are copied from the already validated input.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

import github_intake_docs_patch as docs_patch
import github_intake_docs_patch_worker as worker


DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "rationale", "confidence"],
    "properties": {
        "verdict": {"type": "string", "enum": ["no-impact", "docs-sufficient", "docs-change-required", "inconclusive"]},
        "rationale": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def cagent_config(endpoint: str, model: str) -> str:
    """Return cagent v1.23 configuration with strict output and no toolsets."""
    config = {
        "version": "1", "providers": {"techdocs": {"type": "openai_chatcompletions", "base_url": endpoint, "api_key": "${GC_TECHDOCS_MODEL_TOKEN}", "models": [{"id": model}]}},
        "agents": {"techdocs": {"model": f"techdocs/{model}", "reasoning_effort": "medium", "toolsets": [], "structured_output": {"schema": DECISION_SCHEMA, "strict": True}}},
        "default_agent": "techdocs",
    }
    return json.dumps(config, sort_keys=True)


def decision_from_jsonl(raw: str) -> dict[str, Any]:
    chunks: list[str] = []
    for line in raw.splitlines():
        event = json.loads(line)
        if isinstance(event, dict) and event.get("type") == "agent_choice" and isinstance(event.get("content"), str):
            chunks.append(event["content"])
    value = json.loads("".join(chunks))
    if not isinstance(value, dict) or set(value) != {"verdict", "rationale", "confidence"}:
        raise ValueError("cagent did not return the strict decision document")
    if value["verdict"] not in DECISION_SCHEMA["properties"]["verdict"]["enum"]:
        raise ValueError("cagent returned unsupported verdict")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip() or type(value["confidence"]) not in (int, float) or not 0 <= value["confidence"] <= 1:
        raise ValueError("cagent returned malformed decision")
    return value


def review_assignment(raw: bytes, skill_dir: pathlib.Path, endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    assignment = worker.load_assignment_bytes(raw)
    prompts = [skill_dir / "SKILL.md", *(skill_dir / "references").glob("*.md")]
    if not endpoint or not model or any(not item.is_file() for item in prompts):
        raise ValueError("sidecar requires model endpoint, model, and complete vendored skill")
    with tempfile.TemporaryDirectory(prefix="city-techdocs-") as directory:
        root = pathlib.Path(directory)
        config = root / "agent.yaml"; config.write_text(cagent_config(endpoint, model), encoding="utf-8")
        command = ["/usr/local/bin/cagent", "exec", str(config), "--json", "--session-db", str(root / "session.db")]
        for prompt in prompts:
            command.extend(["--prompt-file", str(prompt)])
        command.extend(["-"])
        result = subprocess.run(command, input=docs_patch.canonical_json(assignment) + "\n", text=True, capture_output=True,
                                env={"HOME": "/tmp", "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TELEMETRY_ENABLED": "false", "GC_TECHDOCS_MODEL_TOKEN": os.environ.get("GC_TECHDOCS_MODEL_TOKEN", "")}, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError("cagent review failed")
    decision = decision_from_jsonl(result.stdout)
    first = assignment["evidence_bundle"]["files"][0]
    return docs_patch.validate_agent_review({"schema_version": 1, "kind": "github-pr-docs-impact-review", "identity": assignment["identity"], "agent_skill": assignment["agent_skill"], "verdict": decision["verdict"], "rationale": decision["rationale"].strip(), "evidence": [{"path": first["path"], "evidence": first["reference"]}], "confidence": float(decision["confidence"]), "proposal": None})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignment-file", required=True); parser.add_argument("--review-file", required=True); parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--endpoint", default=os.environ.get("GC_TECHDOCS_MODEL_ENDPOINT", "")); parser.add_argument("--model", default=os.environ.get("GC_TECHDOCS_MODEL", "gpt-5.6-terra")); parser.add_argument("--timeout-seconds", type=float, default=300)
    args = parser.parse_args()
    try:
        review = review_assignment(pathlib.Path(args.assignment_file).read_bytes(), pathlib.Path(args.skill_dir), args.endpoint, args.model, args.timeout_seconds)
        pathlib.Path(args.review_file).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.review_file).write_text(docs_patch.canonical_json(review) + "\n", encoding="utf-8")
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
