"""Pure, durable state transitions for an explicit docs bootstrap root.

This module deliberately does not inspect TechDocs reasoning or perform GitHub
or City effects.  Callers persist its returned records, then project the
returned action intents idempotently.
"""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
from typing import Any

import github_intake_docs_patch as docs_patch


TERMINAL_STATES = frozenset({
    "baseline-complete",
    "owner-review-required",
    "blocked-on-product-decision",
    "budget-exhausted",
    "cancelled",
})
DEFAULT_BUDGETS = {
    "max_depth": 2,
    "max_children": 8,
    "max_docs_prs": 4,
    "max_elapsed_seconds": 24 * 60 * 60,
    "max_non_progress": 3,
}
_COMPLETE_CHILD_STATES = frozenset({"complete", "cancelled", "blocked", "failed"})


def new_root(request: dict[str, Any], now: float) -> dict[str, Any]:
    """Create one explicit, immutable-snapshot bootstrap root record."""
    if not isinstance(request, dict) or request.get("explicit") is not True:
        raise ValueError("docs bootstrap roots must be explicit")
    repository_id = _required_text(request, "repository_id")
    repository = _required_text(request, "repository")
    installation_id = _required_text(request, "installation_id")
    root_issue_url = _required_text(request, "root_issue_url")
    default_branch = _required_text(request, "default_branch")
    root_issue_number = request.get("root_issue_number")
    if type(root_issue_number) is not int or root_issue_number <= 0:
        raise ValueError("root_issue_number must be a positive integer")
    snapshot_sha = _sha(request.get("default_branch_sha"), "default_branch_sha")
    budgets = _budgets(request)
    identity = f"github-docs-bootstrap:{repository_id}:{root_issue_number}:{snapshot_sha}"
    return {
        "schema_version": 1,
        "identity": identity,
        "explicit": True,
        "repository_id": repository_id,
        "repository": repository,
        "installation_id": installation_id,
        "root_issue_number": root_issue_number,
        "root_issue_url": root_issue_url,
        "default_branch": default_branch,
        "default_branch_sha": snapshot_sha,
        "created_at": now,
        "state": "active",
        "budgets": budgets,
        "children": [],
        "actions": [],
        "visited_surfaces": [],
        "children_used": 0,
        "docs_prs_used": 0,
        "non_progress_count": 0,
    }


def admit_child(root: dict[str, Any], decision: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Mechanically admit one exact docs-impact decision, or return no action.

    A malformed or unrelated decision is inert.  The only semantic field read
    is the producer's machine verdict; rationale is deliberately opaque.
    """
    updated = _copy_root(root)
    if updated["state"] in TERMINAL_STATES:
        return updated, None
    # A foreign or malformed document is inert.  It must never obtain the
    # authority to terminalize a durable root by claiming ambiguity or stale
    # provenance.
    normalized = _exact_decision(updated, decision)
    if normalized is None:
        return updated, None
    terminal = _admission_terminal(updated, normalized, now)
    if terminal is not None:
        return _terminal(updated, terminal)
    key = _child_key(updated["identity"], normalized["identity"], normalized["paths"])
    if any(child.get("key") == key for child in updated["children"]):
        return updated, None
    if any(path in updated["visited_surfaces"] for path in normalized["paths"]):
        return updated, None
    depth = normalized["depth"]
    budgets = updated["budgets"]
    if depth > budgets["max_depth"] or updated["children_used"] >= budgets["max_children"] or updated["docs_prs_used"] >= budgets["max_docs_prs"]:
        return _terminal(updated, "budget-exhausted")
    child = {
        "key": key,
        "root_issue_url": updated["root_issue_url"],
        "parent_issue_url": updated["root_issue_url"],
        "depth": depth,
        "bootstrap_identity": updated["identity"],
        "snapshot_sha": updated["default_branch_sha"],
        "decision_identity": normalized["identity"],
        "decision_digest": normalized["digest"],
        "evidence_paths": normalized["paths"],
        "state": "admitted",
    }
    updated["children"].append(child)
    updated["children_used"] += 1
    updated["visited_surfaces"] = sorted(set(updated["visited_surfaces"]) | set(normalized["paths"]))
    action = _action(f"bootstrap-child:{key}:create_issue", "create_issue", child_key=key)
    updated["actions"].append(action)
    return updated, action


def reconcile_root(root: dict[str, Any], now: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Re-emit pending intents and make one deterministic terminal transition."""
    updated = _copy_root(root)
    if updated["state"] in TERMINAL_STATES:
        return updated, _pending(updated)
    state = _reconcile_terminal(updated, now)
    if state is not None:
        updated, action = _terminal(updated, state)
        return updated, [action]
    pending = _pending(updated)
    if pending:
        updated["non_progress_count"] += 1
        if updated["non_progress_count"] >= updated["budgets"]["max_non_progress"]:
            updated, action = _terminal(updated, "budget-exhausted")
            return updated, [action]
        return updated, pending
    updated["non_progress_count"] = 0
    return updated, []


def _admission_terminal(root: dict[str, Any], decision: dict[str, Any], now: float) -> str | None:
    if root.get("cancelled") is True:
        return "cancelled"
    if root.get("owner_review_required") is True:
        return "owner-review-required"
    if root.get("product_decision_required") is True:
        return "blocked-on-product-decision"
    if now - root["created_at"] >= root["budgets"]["max_elapsed_seconds"]:
        return "budget-exhausted"
    if decision["product_ambiguity"]:
        return "blocked-on-product-decision"
    if decision["snapshot_sha"] != root["default_branch_sha"]:
        return "owner-review-required"
    return None


def _reconcile_terminal(root: dict[str, Any], now: float) -> str | None:
    if root.get("cancelled") is True:
        return "cancelled"
    if root.get("owner_review_required") is True or root.get("snapshot_current") is False:
        return "owner-review-required"
    if root.get("product_decision_required") is True:
        return "blocked-on-product-decision"
    if now - root["created_at"] >= root["budgets"]["max_elapsed_seconds"]:
        return "budget-exhausted"
    budgets = root["budgets"]
    if root["children_used"] >= budgets["max_children"] or root["docs_prs_used"] >= budgets["max_docs_prs"]:
        return "budget-exhausted"
    children = root["children"]
    if children and all(child.get("state") in _COMPLETE_CHILD_STATES for child in children):
        return "baseline-complete"
    return None


def _exact_decision(root: dict[str, Any], decision: Any) -> dict[str, Any] | None:
    """Validate the established TechDocs artifact before deriving controller data."""
    if not isinstance(decision, dict):
        return None
    try:
        artifact: Any = decision
        product_ambiguity = False
        depth = 1
        if "artifact" in decision:
            if set(decision) - {"artifact", "product_ambiguity", "depth"}:
                return None
            artifact = decision["artifact"]
            product_ambiguity = decision.get("product_ambiguity", False)
            depth = decision.get("depth", 1)
            if type(product_ambiguity) is not bool:
                return None
        review = docs_patch.validate_agent_review(artifact)
        if review["verdict"] != "docs-change-required":
            return None
        identity = review["identity"]
        if identity["repository_id"] != root["repository_id"] or identity["repository"] != root["repository"]:
            return None
    except ValueError:
        return None
    if type(depth) is not int or depth < 1:
        return None
    paths = _normalized_paths(review["evidence"])
    return {
        "identity": {"source_key": identity["source_key"], "review_sha256": review["review_sha256"]},
        "paths": paths,
        "depth": depth,
        "digest": review["review_sha256"],
        "snapshot_sha": identity["head_sha"],
        "product_ambiguity": product_ambiguity,
    }


def _terminal(root: dict[str, Any], state: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root["state"] = state
    action_id = f"bootstrap-root:{root['identity']}:status:{state}"
    action = next((item for item in root["actions"] if item.get("id") == action_id), None)
    if action is None:
        action = _action(action_id, "post_root_status", state=state)
        root["actions"].append(action)
    return root, action


def _pending(root: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(action) for action in root["actions"] if action.get("state") == "pending"]


def _action(action_id: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {"id": action_id, "kind": kind, "state": "pending", **fields}


def _copy_root(root: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(root, dict) or root.get("state") not in {"active", *TERMINAL_STATES}:
        raise ValueError("root is invalid")
    result = copy.deepcopy(root)
    for key in ("children", "actions", "visited_surfaces"):
        if not isinstance(result.get(key), list):
            raise ValueError(f"root {key} must be a list")
    result["budgets"] = _validate_budgets(result.get("budgets"))
    for key in ("children_used", "docs_prs_used", "non_progress_count"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError(f"root {key} must be a non-negative integer")
    return result


def _budgets(request: dict[str, Any]) -> dict[str, int]:
    raw = request.get("budgets")
    if raw is None:
        raw = {key: request[key] for key in DEFAULT_BUDGETS if key in request}
    if not isinstance(raw, dict):
        raise ValueError("budgets must be an object")
    return _validate_budgets({**DEFAULT_BUDGETS, **raw})


def _validate_budgets(budgets: Any) -> dict[str, int]:
    if not isinstance(budgets, dict):
        raise ValueError("budgets must be an object")
    result: dict[str, int] = {}
    for key in DEFAULT_BUDGETS:
        value = budgets.get(key)
        if type(value) is not int or value <= 0:
            raise ValueError(f"budget {key} must be a positive integer")
        result[key] = value
    return result


def _required_text(value: dict[str, Any], key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{key} is required")
    return text.strip()


def _normalized_paths(evidence: list[dict[str, str]]) -> list[str]:
    """Deduplicate canonical evidence-surface paths after artifact validation."""
    return sorted({posixpath.normpath(item["path"]) for item in evidence})


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError(f"{name} must be a 40-character SHA")
    return value.lower()


def _child_key(root_identity: str, decision_identity: dict[str, str], paths: list[str]) -> str:
    binding = {"root_identity": root_identity, "decision_identity": decision_identity, "evidence_paths": paths}
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
