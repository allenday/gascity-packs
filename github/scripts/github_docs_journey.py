"""Pure, durable state transitions for source-agnostic documentation journeys.

This module does not inspect TechDocs reasoning.  Non-blocking debt is an
inactive leaf with no descendants; active continuation exists only on a
blocking edge of the explicit journey.  Production callers persist returned
records, then project action intents through the configured GitHub App and
City Beads adapters.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import pathlib
import posixpath
import tempfile
import time
import urllib.parse
from typing import Any

import github_intake_common as common
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
    "max_debt_issues": 8,
    "max_elapsed_seconds": 24 * 60 * 60,
    "max_non_progress": 3,
}
_COMPLETE_CHILD_STATES = frozenset({"complete", "cancelled", "blocked", "failed"})


def new_root(request: dict[str, Any], now: float) -> dict[str, Any]:
    """Create a legacy v1 bootstrap record.

    New callers must use :func:`new_journey`.  This constructor intentionally
    remains byte-compatible with persisted v1 records so a replay continues to
    adopt its existing external action IDs instead of projecting duplicates.
    """
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
    journey = _journey(request)
    documentation_root = select_documentation_root(request)
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
        "documentation_root": documentation_root,
        "journey": journey,
        "created_at": now,
        "state": "active",
        "budgets": budgets,
        "children": [],
        "debts": [],
        "actions": [],
        "visited_surfaces": [],
        "children_used": 0,
        "docs_prs_used": 0,
        "debt_issues_used": 0,
        "non_progress_count": 0,
    }


def new_journey(request: dict[str, Any], now: float) -> dict[str, Any]:
    """Create a v2 journey run from a normalized request and source envelope.

    The source is provenance, not a privileged execution root.  GitHub issues,
    pull requests, and operator requests can therefore share this same durable
    model once their adapters normalize to the contract below.
    """
    if not isinstance(request, dict):
        raise ValueError("documentation journey request must be an object")
    if "context" in request or "persona_goal_path" in request:
        return _new_recursion(request, now)
    repository_id = _required_text(request, "repository_id")
    repository = _required_text(request, "repository")
    installation_id = _required_text(request, "installation_id")
    default_branch = _required_text(request, "default_branch")
    snapshot_sha = _sha(request.get("default_branch_sha"), "default_branch_sha")
    source = _source(request.get("source"))
    docs_impact_source_key = _required_text(request, "docs_impact_source_key")
    journey = _journey(request)
    documentation_root = select_documentation_root(request)
    return {
        "schema_version": 2,
        "identity": f"github-docs-journey:{repository_id}:{source['key']}:{snapshot_sha}",
        "repository_id": repository_id,
        "repository": repository,
        "installation_id": installation_id,
        "source": source,
        # A request source may intentionally bridge to a docs-impact review
        # source, but the bridge is declared once in the durable contract.
        "docs_impact_source_key": docs_impact_source_key,
        "default_branch": default_branch,
        "default_branch_sha": snapshot_sha,
        "documentation_root": documentation_root,
        "journey": journey,
        "created_at": now,
        "state": "active",
        "budgets": _budgets(request),
        "children": [],
        "debts": [],
        "actions": [],
        "visited_surfaces": [],
        "children_used": 0,
        "docs_prs_used": 0,
        "debt_issues_used": 0,
        "non_progress_count": 0,
    }


def select_documentation_root(request: dict[str, Any]) -> str:
    """Select the declared documentation index, falling back to ``README.md``."""
    if not isinstance(request, dict):
        raise ValueError("documentation-root request must be an object")
    if "documentation_index" not in request:
        return "README.md"
    path = request["documentation_index"]
    if not isinstance(path, str) or not path.strip():
        raise ValueError("documentation_index must be a non-empty path")
    normalized = posixpath.normpath(path.strip())
    if normalized in {".", ".."} or normalized.startswith("../") or normalized.startswith("/"):
        raise ValueError("documentation_index is unsafe")
    return normalized


def begin_traversal(
    request: dict[str, Any], decision: dict[str, Any], now: float, *, existing_root: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Compatibility entry point for former bootstrap callers.

    Only an already-persisted v1 record follows the old bound-root path.  New
    work is normalized into a v2 journey, so this wrapper cannot create a new
    bootstrap root.
    """
    if not isinstance(request, dict):
        raise ValueError("traversal request must be an object")
    pull_request = request.get("pull_request")
    if pull_request is not None and existing_root is not None and existing_root.get("schema_version") == 1:
        if not isinstance(pull_request, dict) or existing_root is None:
            return None, None
        root = _copy_root(existing_root)
        if pull_request.get("bootstrap_identity") != root["identity"]:
            return None, None
        if select_documentation_root(request) != root.get("documentation_root"):
            return None, None
        return admit_child(root, decision, now)
    if existing_root is not None:
        return None, None
    candidate_request = copy.deepcopy(request)
    if pull_request is not None:
        # The legacy adapter has no normalized PR source envelope.  Leave it
        # inert rather than synthesize provenance or create unrelated work.
        return None, None
    candidate_request.pop("explicit", None)
    candidate_request.setdefault("source", {
        "kind": "github-issue",
        "key": f"github-issue:{_required_text(candidate_request, 'repository_id')}:{candidate_request['root_issue_number']}",
        "url": _required_text(candidate_request, "root_issue_url"),
        "issue_number": candidate_request["root_issue_number"],
        "projection_capabilities": ["issue-comment"],
    })
    return begin_journey(candidate_request, decision, now)


def begin_journey(
    request: dict[str, Any], decision: dict[str, Any], now: float, *, existing_journey: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Start or continue the declared source-bound documentation journey.

    Unlike the v1 bootstrap path, a source that is not bound to a persisted
    journey may start its own complete journey.  It cannot attach to or expand
    another source's run merely by replaying a docs-impact artifact.
    """
    if not isinstance(request, dict):
        raise ValueError("journey request must be an object")
    if existing_journey is not None:
        journey = _copy_root(existing_journey)
        if not journey_request_matches(journey, request):
            return None, None
        return admit_child(journey, decision, now)
    candidate = new_journey(request, now)
    normalized = _exact_decision(candidate, decision)
    if normalized is None:
        return None, None
    if (candidate.get("schema_version") == 2 and normalized["journey_disposition"] == "non-blocking"
            and candidate["journey"]["backfill_policy"] == "blocking-only"):
        return None, None
    return admit_child(candidate, decision, now)


def _new_recursion(request: dict[str, Any], now: float) -> dict[str, Any]:
    """Create the current single-recursion record.

    Version 3 intentionally gives every entry point the same surface: context
    is immutable provenance, and persona_goal_path is the only traversal
    declaration.  v1/v2 constructors above remain readable for replay.
    """
    repository_id = _required_text(request, "repository_id")
    repository = _required_text(request, "repository")
    installation_id = _required_text(request, "installation_id")
    context = _context({**(request.get("context") if isinstance(request.get("context"), dict) else {}),
                        "repository_id": repository_id, "repository": repository,
                        "installation_id": installation_id})
    path = _persona_goal_path(request.get("persona_goal_paths", request.get("persona_goal_path")))
    budgets = _recursion_budgets(request.get("execution_budgets", request.get("budgets")))
    return {
        "schema_version": 3,
        "identity": f"github-docs-recursion:{repository_id}:{context['key']}:{context['default_branch_sha']}",
        "context": context,
        "persona_goal_path": path,
        "execution_budgets": budgets,
        "coverage_cells": _coverage_cells(request.get("coverage_cells")),
        "coverage_results": [],
        "children": [],
        "buds": [],
        "actions": [],
        "state": "active",
        "created_at": now,
        "children_used": 0,
        "docs_prs_used": 0,
        "non_progress_count": 0,
        "visited_surfaces": [],
    }


def journey_request_matches(existing_journey: dict[str, Any], request: dict[str, Any]) -> bool:
    """Return whether ``request`` is the immutable contract of a v2 run.

    A stable source key alone is not an authorization to resume a journey:
    source URL/capabilities, repository binding, snapshot, entry point,
    reader journey, and every budget are all part of that binding.
    """
    try:
        existing = _copy_root(existing_journey)
        candidate = new_journey(request, now=existing["created_at"])
    except (KeyError, ValueError):
        return False
    if existing.get("schema_version") == 3:
        fields = ("identity", "context", "persona_goal_path", "coverage_cells", "execution_budgets")
        return all(existing.get(field) == candidate.get(field) for field in fields)
    if existing.get("schema_version") != 2:
        return False
    fields = (
        "identity", "repository_id", "repository", "installation_id", "source",
        "docs_impact_source_key", "default_branch", "default_branch_sha", "documentation_root", "journey", "budgets",
    )
    return all(existing.get(field) == candidate.get(field) for field in fields)


def admit_child(root: dict[str, Any], decision: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Mechanically admit one exact docs-impact decision, or return no action.

    A malformed or unrelated decision is inert.  The only semantic field read
    is the producer's machine verdict; rationale is deliberately opaque.
    """
    updated = _copy_root(root)
    if updated.get("schema_version") == 3:
        return _admit_recursion(updated, decision, now)
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
    if normalized["journey_disposition"] == "non-blocking":
        return _admit_debt(updated, normalized, key)
    depth = normalized["depth"]
    budgets = updated["budgets"]
    if depth > budgets["max_depth"] or updated["children_used"] >= budgets["max_children"] or updated["docs_prs_used"] >= budgets["max_docs_prs"]:
        return _terminal(updated, "budget-exhausted")
    child = {
        "key": key,
        "depth": depth,
        "snapshot_sha": updated["default_branch_sha"],
        "decision_identity": normalized["identity"],
        "decision_digest": normalized["digest"],
        "evidence_paths": normalized["paths"],
        "state": "admitted",
    }
    if updated.get("schema_version") == 1:
        child.update({
            "root_issue_url": updated["root_issue_url"],
            "parent_issue_url": updated["root_issue_url"],
            "bootstrap_identity": updated["identity"],
        })
    else:
        child.update({
            "journey_identity": updated["identity"],
            "source_key": updated["source"]["key"],
            "source_url": updated["source"]["url"],
            "documentation_entry_point": updated["documentation_root"],
            "parent_issue_url": updated["source"]["url"],
        })
    updated["children"].append(child)
    updated["children_used"] += 1
    updated["visited_surfaces"] = sorted(set(updated["visited_surfaces"]) | set(normalized["paths"]))
    action = _action(f"{_action_prefix(updated)}-child:{key}:create_issue", "create_issue", child_key=key)
    updated["actions"].append(action)
    return updated, action


def record_child_update(root: dict[str, Any], update: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Record one qualified worker result and stage its optional App PR.

    This is deliberately a root-driver operation, not an ordinary pull-request
    intake path.  The worker can update only an already admitted child whose
    provenance it echoes exactly; it cannot admit another review decision.
    """
    updated = _copy_root(root)
    if updated["state"] in TERMINAL_STATES or not isinstance(update, dict):
        return updated, None
    expected_kind = {1: "github-docs-bootstrap-child-update", 2: "github-docs-journey-child-update", 3: "github-docs-recursion-child-update"}[updated["schema_version"]]
    if update.get("schema_version") != 1 or update.get("kind") != expected_kind:
        return updated, None
    admitted = update.get("admitted_child")
    if not isinstance(admitted, dict):
        return updated, None
    child = next((item for item in updated["children"] if (
        item.get("identity") == admitted.get("identity") if updated.get("schema_version") == 3 else _same_child_provenance(item, admitted)
    )), None)
    if child is None or child.get("state") != "admitted":
        return updated, None
    state = update.get("state")
    if state not in _COMPLETE_CHILD_STATES:
        return updated, None
    branch_is_valid, documentation_branch = _worker_documentation_branch(updated, update)
    if not branch_is_valid:
        return updated, None
    child["state"] = state
    if documentation_branch is None:
        return updated, None
    if updated["docs_prs_used"] >= _execution_budgets(updated)["max_docs_prs"]:
        return _terminal(updated, "budget-exhausted")
    action_id = _child_action_id(child, "create_docs_pr")
    if any(action.get("id") == action_id for action in updated["actions"]):
        return updated, None
    action = _action(
        action_id, "create_docs_pr", child_key=child["key"],
        branch=documentation_branch["branch"] if isinstance(documentation_branch, dict) else documentation_branch,
        # The worker can attest only to its App-owned branch and evidence.
        # The controller, not an untrusted child update, owns public PR intent.
        title=f"{_run_label(updated)} follow-up: {child['key'][:12]}",
        body=_documentation_pr_body(updated, child),
        base=updated["context"]["default_branch"] if updated.get("schema_version") == 3 else updated["default_branch"],
        worker_evidence=copy.deepcopy(update["documentation_branch"]["evidence"])
        if updated.get("schema_version") in {2, 3} else [],
    )
    if isinstance(documentation_branch, dict):
        action["commit_sha"] = documentation_branch["commit_sha"]
    updated["actions"].append(action)
    updated["docs_prs_used"] += 1
    return updated, action


def _worker_documentation_branch(root: dict[str, Any], update: dict[str, Any]) -> tuple[bool, dict[str, Any] | str | None]:
    """Accept the bounded worker branch/evidence contract for v2 journeys.

    v1 records retain their historic ``documentation_pr`` payload so recovery
    of already-issued bootstrap work remains possible.  A v2 worker may not
    choose a pull-request title, body, or base branch.
    """
    if root.get("schema_version") == 1:
        documentation_pr = update.get("documentation_pr")
        if documentation_pr is None:
            return True, None
        if not isinstance(documentation_pr, dict):
            return False, None
        branch = documentation_pr.get("branch")
        return (True, branch) if isinstance(branch, str) and branch.startswith("gas-city/") else (False, None)
    if "documentation_pr" in update:
        return False, None
    branch_update = update.get("documentation_branch")
    if branch_update is None:
        return True, None
    if not isinstance(branch_update, dict) or set(branch_update) != {"branch", "commit_sha", "evidence"}:
        return False, None
    branch = branch_update.get("branch")
    commit_sha = branch_update.get("commit_sha")
    evidence = branch_update.get("evidence")
    if not isinstance(branch, str) or not branch.startswith("gas-city/"):
        return False, None
    if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
        return False, None
    try:
        return True, {"branch": branch, "commit_sha": _sha(commit_sha, "documentation_branch.commit_sha"), "evidence": evidence}
    except ValueError:
        return False, None


def _documentation_pr_body(root: dict[str, Any], child: dict[str, Any]) -> str:
    """Build deterministic public PR context from admitted controller data."""
    source = root.get("context", root.get("source", {}))
    source_url = source.get("url") if isinstance(source, dict) else None
    lines = [f"App-owned {_run_label(root).lower()} follow-up."]
    if isinstance(source_url, str) and source_url:
        lines.extend(("", f"Source: {source_url}"))
    lines.extend(("", "Admitted evidence surfaces:", *(f"- `{path}`" for path in child["evidence_paths"])))
    return "\n".join(lines)


def _same_child_provenance(child: dict[str, Any], admitted: dict[str, Any]) -> bool:
    fields = (
        "snapshot_sha", "decision_identity", "decision_digest", "parent_issue_url", "evidence_paths",
    )
    if "journey_identity" in child:
        fields += ("journey_identity", "source_key", "source_url", "documentation_entry_point")
    else:
        fields += ("bootstrap_identity", "root_issue_url")
    return all(admitted.get(field) == child.get(field) for field in fields)


def _admit_debt(root: dict[str, Any], decision: dict[str, Any], key: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Record one non-executing documentation debt, never active work."""
    if any(debt.get("key") == key for debt in root["debts"]):
        return root, None
    if root["journey"]["backfill_policy"] == "blocking-only":
        root["visited_surfaces"] = sorted(set(root["visited_surfaces"]) | set(decision["paths"]))
        return root, None
    if root["debt_issues_used"] >= root["budgets"]["max_debt_issues"]:
        return _terminal(root, "budget-exhausted")
    root["visited_surfaces"] = sorted(set(root["visited_surfaces"]) | set(decision["paths"]))
    debt = {
        "key": key,
        "snapshot_sha": root["default_branch_sha"],
        "decision_identity": decision["identity"],
        "decision_digest": decision["digest"],
        "evidence_paths": decision["paths"],
        "state": "recorded",
    }
    if root.get("schema_version") == 1:
        debt.update({"root_issue_url": root["root_issue_url"], "bootstrap_identity": root["identity"]})
    else:
        debt.update({"journey_identity": root["identity"], "source_key": root["source"]["key"], "source_url": root["source"]["url"]})
    root["debts"].append(debt)
    root["debt_issues_used"] += 1
    action = _action(f"{_action_prefix(root)}-debt:{key}:create_debt_issue", "create_debt_issue", debt_key=key)
    root["actions"].append(action)
    return root, action


def _admit_recursion(root: dict[str, Any], decision: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Admit exactly one on-path child or record exactly one inert bud."""
    if root["state"] in TERMINAL_STATES:
        return root, None
    normalized = _exact_decision(root, decision)
    if normalized is None:
        return root, None
    cells = decision.get("coverage_cells") if isinstance(decision, dict) else None
    normalized_cells = _normalize_coverage_assessment(root, cells)
    if normalized_cells is None:
        return root, None
    # All results are validated before any durable state is changed.
    updated = copy.deepcopy(root)
    updated["coverage_results"] = normalized_cells
    if any(cell["classification"] == "human-required" for cell in normalized_cells):
        return _terminal(updated, "owner-review-required")
    actions: list[dict[str, Any]] = []
    active_selected = False
    for cell in normalized_cells:
        if cell["classification"] != "unmet":
            continue
        cell_normalized = copy.deepcopy(normalized)
        cell_normalized["identity"] = {**normalized["identity"], "coverage_cell": cell["identity"]}
        cell_normalized["paths"] = cell["evidence_paths"]
        cell_normalized["journey_disposition"] = "blocking" if not active_selected else "non-blocking"
        before = len(updated["children"])
        updated, action = _admit_recursion_from_normalized(updated, cell_normalized, now)
        active_selected = active_selected or len(updated["children"]) > before
        if action is not None:
            actions.append(action)
    return updated, actions[0] if actions else None


def _normalize_coverage_assessment(root: dict[str, Any], cells: Any) -> list[dict[str, Any]] | None:
    if not isinstance(cells, list) or len(cells) != len(root["coverage_cells"]):
        return None
    declared = [item["identity"] for item in root["coverage_cells"]]
    results: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {"identity", "classification", "evidence_paths"}:
            return None
        identity, classification, paths = cell["identity"], cell["classification"], cell["evidence_paths"]
        if not isinstance(identity, str) or classification not in {"sufficient", "unmet", "human-required"}:
            return None
        if not isinstance(paths, list) or not paths or any(not isinstance(path, str) or not path for path in paths):
            return None
        results.append({"identity": identity, "classification": classification, "evidence_paths": sorted(set(paths))})
    if [item["identity"] for item in results] != declared:
        return None
    existing = root["coverage_results"]
    return results if not existing or existing == results else None


def _admit_recursion_from_normalized(root: dict[str, Any], normalized: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    terminal = _admission_terminal(root, normalized, now)
    if terminal is not None:
        return _terminal(root, terminal)
    key = _child_key(root["identity"], normalized["identity"], normalized["paths"])
    if normalized["journey_disposition"] == "non-blocking":
        return _record_recursion_bud(root, normalized, key)
    if any(child.get("key") == key for child in root["children"]) or any(path in root["visited_surfaces"] for path in normalized["paths"]):
        return root, None
    if (normalized["depth"] > root["execution_budgets"]["max_depth"] or root["children_used"] >= root["execution_budgets"]["max_children"]
            or root["docs_prs_used"] >= root["execution_budgets"]["max_docs_prs"]):
        return _record_recursion_bud(root, normalized, key)
    child = {"key": key, "identity": key, "state": "admitted", "depth": normalized["depth"],
             "snapshot_sha": root["context"]["default_branch_sha"], "decision_identity": normalized["identity"],
             "decision_digest": normalized["digest"], "evidence_paths": normalized["paths"],
             "context": copy.deepcopy(root["context"]), "persona_goal_path": copy.deepcopy(root["persona_goal_path"])}
    root["children"].append(child)
    root["children_used"] += 1
    root["visited_surfaces"] = sorted(set(root["visited_surfaces"]) | set(normalized["paths"]))
    action = _action(f"docs-recursion-child:{key}:create_issue", "create_issue", child_key=key)
    root["actions"].append(action)
    return root, action


def _record_recursion_bud(root: dict[str, Any], normalized: dict[str, Any], key: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if any(bud.get("identity") == key for bud in root["buds"]):
        return root, None
    bud = {"identity": key, "state": "recorded", "context": copy.deepcopy(root["context"]),
           "persona_goal_path": copy.deepcopy(root["persona_goal_path"]),
           "decision_identity": normalized["identity"], "decision_digest": normalized["digest"],
           "evidence_paths": normalized["paths"]}
    root["buds"].append(bud)
    root["visited_surfaces"] = sorted(set(root["visited_surfaces"]) | set(normalized["paths"]))
    # Task 2 owns GitHub issue reconciliation.  Reuse the long-standing
    # durable intent kind so existing configured adapters remain safe.
    action = _action(f"docs-recursion-bud:{key}:create_debt_issue", "create_debt_issue", bud_identity=key)
    root["actions"].append(action)
    return root, action


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
        if updated["non_progress_count"] >= _execution_budgets(updated)["max_non_progress"]:
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
    if now - root["created_at"] >= _execution_budgets(root)["max_elapsed_seconds"]:
        return "budget-exhausted"
    if decision["product_ambiguity"]:
        return "blocked-on-product-decision"
    if decision["snapshot_sha"] != _snapshot_sha(root):
        return "owner-review-required"
    return None


def _reconcile_terminal(root: dict[str, Any], now: float) -> str | None:
    if root.get("cancelled") is True:
        return "cancelled"
    if root.get("owner_review_required") is True or root.get("snapshot_current") is False:
        return "owner-review-required"
    if root.get("product_decision_required") is True:
        return "blocked-on-product-decision"
    if now - root["created_at"] >= _execution_budgets(root)["max_elapsed_seconds"]:
        return "budget-exhausted"
    children = root["children"]
    if children and all(child.get("state") in _COMPLETE_CHILD_STATES for child in children):
        return "baseline-complete"
    if root.get("schema_version") == 3:
        # Active-work allocation is not a terminal condition.  The admitted
        # child and all inert buds remain durable/replayable until a real
        # completion, cancellation, stale snapshot, or elapsed-time outcome.
        return None
    budgets = _execution_budgets(root)
    if (root["children_used"] >= budgets["max_children"] or root["docs_prs_used"] >= budgets["max_docs_prs"]
            or root["debt_issues_used"] >= budgets["max_debt_issues"]):
        return "budget-exhausted"
    return None


def _forced_terminal(root: dict[str, Any], now: float) -> str | None:
    """Return terminal states that safely preempt already-staged work."""
    if root.get("cancelled") is True:
        return "cancelled"
    if root.get("owner_review_required") is True or root.get("snapshot_current") is False:
        return "owner-review-required"
    if root.get("product_decision_required") is True:
        return "blocked-on-product-decision"
    if now - root["created_at"] >= _execution_budgets(root)["max_elapsed_seconds"]:
        return "budget-exhausted"
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
            if set(decision) - {"artifact", "product_ambiguity", "depth", "journey_disposition", "coverage_cells"}:
                return None
            artifact = decision["artifact"]
            product_ambiguity = decision.get("product_ambiguity", False)
            depth = decision.get("depth", 1)
            journey_disposition = decision.get("journey_disposition")
            if type(product_ambiguity) is not bool:
                return None
            if journey_disposition not in {"blocking", "non-blocking"}:
                return None
        else:
            return None
        review = docs_patch.validate_agent_review(artifact)
        if review["verdict"] != "docs-change-required":
            return None
        identity = review["identity"]
        if identity["repository_id"] != _repository_id(root) or identity["repository"] != _repository(root):
            return None
        if root.get("schema_version") == 2 and identity["source_key"] != root.get("docs_impact_source_key"):
            return None
        if root.get("schema_version") == 3 and identity["source_key"] != root["context"]["docs_impact_source_key"]:
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
        "journey_disposition": journey_disposition,
    }


def _terminal(root: dict[str, Any], state: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root["state"] = state
    prefix = "bootstrap-root" if root.get("schema_version") == 1 else "docs-journey"
    action_id = f"{prefix}:{root['identity']}:status:{state}"
    action = next((item for item in root["actions"] if item.get("id") == action_id), None)
    if action is None:
        # `state` belongs to the durable action lifecycle.  Keep the root's
        # terminal value separate so the status projection remains pending.
        action = _action(action_id, "post_root_status", root_state=state)
        root["actions"].append(action)
    return root, action


def project_actions(
    root: dict[str, Any], adapter: Any, persist: Any = None, pending_action_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Project persisted intents once, adopting effects by their action IDs.

    An action is already persisted as ``pending`` before this function sees
    it.  A caller may therefore crash before, during, or after an adapter
    invocation and replay the same root.  Adapters must use ``action['id']``
    as their external logical ID and return an existing resource when one was
    created by an earlier attempt.  Completion and successor intents are
    recorded only after that adopted/created resource is returned.
    """
    updated = _copy_root(root)
    # Never project an intent appended during this call: the caller must first
    # persist it.  This is the persist-before-action boundary for successors.
    persisted_ids = [
        item.get("id") for item in updated["actions"]
        if item.get("state") == "pending"
        and (pending_action_ids is None or item.get("id") in pending_action_ids)
    ]
    for action_id in persisted_ids:
        action = next(item for item in updated["actions"] if item.get("id") == action_id)
        _project_action(updated, action, adapter)
        # Completion is progress.  Only an explicit reconciliation pass that
        # cannot complete an existing intent may consume this budget.
        updated["non_progress_count"] = 0
        if persist is not None:
            persist(updated)
    return updated


class FileBootstrapStore:
    """Atomic durable storage for explicit bootstrap roots."""

    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root)
        self.roots_dir = self.root / "roots"
        self.journeys_dir = self.root / "journeys"

    def _path(self, identity: str) -> pathlib.Path:
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        directory = self.journeys_dir if identity.startswith("github-docs-journey:") else self.roots_dir
        return directory / f"{digest}.json"

    def load(self, identity: str) -> dict[str, Any] | None:
        paths = [self._path(identity)]
        # v1 records were stored under roots/.  Keep that location readable
        # even if a migration caller addresses a journey identity later.
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        paths.append(self.roots_dir / f"{digest}.json")
        value = None
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                break
            except FileNotFoundError:
                continue
        if value is None:
            return None
        if not isinstance(value, dict) or value.get("identity") != identity:
            raise ValueError("stored bootstrap root is invalid")
        return value

    def save(self, root: dict[str, Any]) -> dict[str, Any]:
        checked = _copy_root(root)
        path = self._path(checked["identity"])
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(json.dumps(checked, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = pathlib.Path(handle.name)
        temporary.replace(path)
        return checked

    def lock(self, identity: str):
        self.roots_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.roots_dir / f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()}.lock"
        return _BootstrapLock(path)


class _BootstrapLock:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> None:
        self.handle = self.path.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        assert self.handle is not None
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def project_persisted_root(store: FileBootstrapStore, identity: str, adapter: Any) -> dict[str, Any]:
    """Load, project, and save one root while serializing restart recovery."""
    with store.lock(identity):
        root = store.load(identity)
        if root is None:
            raise ValueError("bootstrap root was not found")
        # The root was durably written with pending intents before this call.
        return project_actions(root, adapter, persist=store.save)


class GitHubCityBootstrapAdapter:
    """Production projection through the configured GitHub App and City Beads."""

    def __init__(self, app_config: dict[str, Any], city_root: str = "") -> None:
        self.app_config = copy.deepcopy(app_config)
        self.city_root = city_root or common.city_root() or "."
        self.app_login = common.app_bot_login(self.app_config)
        if not self.app_login:
            raise ValueError("GitHub bootstrap projection requires a configured GitHub App slug")

    def create_issue(self, root: dict[str, Any], action: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        return self._issue(root, action, f"{_run_label(root)}: {child['key'][:12]}", child["evidence_paths"])

    def create_debt_issue(self, root: dict[str, Any], action: dict[str, Any], debt: dict[str, Any]) -> dict[str, Any]:
        cell = debt.get("coverage_cell")
        label = f" coverage cell {cell}" if isinstance(cell, str) else ""
        return self._issue(root, action, f"Documentation journey debt{label}: {debt['key'][:12]}", debt["evidence_paths"], debt)

    def _issue(self, root: dict[str, Any], action: dict[str, Any], title: str, evidence_paths: list[str], provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        owner, repo = _repository_parts(root)
        token = common.create_installation_token(self.app_config, str(_installation_id(root)))
        existing = common.find_issue_by_logical_id_with_token(token, owner, repo, str(action["id"]), self.app_login)
        if existing is not None:
            return existing
        lines = [f"App-owned {_run_label(root).lower()} item."]
        if provenance and isinstance(provenance.get("coverage_cell"), str):
            lines.extend(("", f"Coverage cell: `{provenance['coverage_cell']}`.", f"Bud identity: `{provenance['key']}`."))
        lines.extend(("", "Evidence surfaces:", *(f"- `{path}`" for path in evidence_paths)))
        body = "\n".join(lines)
        return common.create_issue_with_token(token, owner, repo, title, body, str(action["id"]))

    def create_bead(self, root: dict[str, Any], action: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        return self._bead(action, f"{_run_label(root)}: {child['key'][:12]}", child["evidence_paths"])

    def assign_bead(self, root: dict[str, Any], action: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        import github_intake_service as service

        bead_action_id = _child_action_id(child, "create_bead")
        bead_action = next((item for item in root["actions"] if item.get("id") == bead_action_id), None)
        resource = bead_action.get("resource") if isinstance(bead_action, dict) else None
        bead_id = str((resource or {}).get("id") or "").strip()
        if not bead_id:
            raise ValueError("assign_bead requires a completed create_bead resource")
        command = service.gc_bd_command(
            self.city_root, "update", bead_id, "--metadata",
            json.dumps({
                "bootstrap.assignment_action_id" if root.get("schema_version") == 1
                else "docs-journey.assignment_action_id": action["id"],
            }, sort_keys=True),
        )
        result = service.run_subprocess(command, self.city_root)
        if result.returncode != 0:
            raise RuntimeError(f"gc bd update failed: {service.trim_output(result.stderr or result.stdout)}")
        return {"id": bead_id, "logical_id": str(action["id"])}

    def post_root_status(self, root: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        owner, repo = _repository_parts(root)
        issue_number = _source_issue_number(root)
        if issue_number is None:
            # A source without GitHub issue-comment capability has no status
            # projection target.  Recording the logical action as adopted is
            # still deterministic and does not invent a cross-source write.
            return {"id": str(action["id"]), "logical_id": str(action["id"])}
        token = common.create_installation_token(self.app_config, str(_installation_id(root)))
        existing = common.find_issue_comment_by_logical_id_with_token(
            token, owner, repo, str(issue_number), str(action["id"]), self.app_login,
        )
        if existing is not None:
            return existing
        state = str(action.get("root_state") or root.get("state") or "")
        body = f"{_run_label(root)} status: `{state}`.\n\n{common.github_logical_id_marker(str(action['id']))}"
        return common.post_issue_comment(self.app_config, str(root["installation_id"]), owner, repo, str(issue_number), body)

    def create_docs_pr(self, root: dict[str, Any], action: dict[str, Any], child: dict[str, Any] | None) -> dict[str, Any]:
        # A docs PR is only allowed from an explicit App-owned branch supplied
        # by the blocking worker; this controller never writes an author branch.
        branch = str(action.get("branch") or "")
        if not branch.startswith("gas-city/"):
            raise ValueError("create_docs_pr requires an App-owned gas-city/ branch")
        owner, repo = _repository_parts(root)
        token = common.create_installation_token(self.app_config, str(root["installation_id"]))
        existing = common.find_pull_request_by_logical_id_with_token(token, owner, repo, str(action["id"]), self.app_login)
        if existing is not None:
            return existing
        if root.get("schema_version") in {2, 3}:
            commit_sha = _sha(action.get("commit_sha"), "documentation branch commit_sha")
            ref = common.github_api_request(
                "GET",
                f"/repos/{owner}/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}",
                bearer_token=token,
            )
            if str((ref.get("object") or {}).get("sha") or "").lower() != commit_sha:
                raise ValueError("documentation branch does not match the admitted immutable commit")
        title = str(action.get("title") or f"{_run_label(root)} follow-up")
        base = str(action.get("base") or (root["context"]["default_branch"] if root.get("schema_version") == 3 else root["default_branch"]))
        body = str(action.get("body") or f"App-owned {_run_label(root).lower()} follow-up.")
        return common.create_pull_request(
            self.app_config, str(_installation_id(root)), owner, repo, title, branch, base,
            body + "\n\n" + common.github_logical_id_marker(str(action["id"])),
        )

    def _bead(self, action: dict[str, Any], title: str, evidence_paths: list[str]) -> dict[str, Any]:
        import github_intake_service as service

        lookup = service.run_subprocess(
            service.gc_bd_command(
                self.city_root, "list", "--json", "--all", "--metadata-field",
                f"external.source_key={action['id']}", "--limit", "0",
            ),
            self.city_root,
        )
        if lookup.returncode != 0:
            raise RuntimeError(f"gc bd list failed: {service.trim_output(lookup.stderr or lookup.stdout)}")
        payload = service.extract_json_value(lookup.stdout)
        existing = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        if existing:
            return {"id": service.bead_id(existing[0]), "logical_id": str(action["id"])}
        command = service.gc_bd_command(
            self.city_root, "create", "--json", title, "-t", "task",
            "--description", "Documentation journey evidence:\n" + "\n".join(evidence_paths),
            "--external-ref", str(action["id"]),
            "--metadata", json.dumps({"external.source_key": str(action["id"])}, sort_keys=True),
        )
        result = service.run_subprocess(command, self.city_root)
        if result.returncode != 0:
            raise RuntimeError(f"gc bd create failed: {service.trim_output(result.stderr or result.stdout)}")
        payload = service.extract_json_value(result.stdout)
        if not isinstance(payload, dict) or not service.bead_id(payload):
            raise RuntimeError("gc bd create did not return a bead")
        return {"id": service.bead_id(payload), "logical_id": str(action["id"])}


def _repository_parts(root: dict[str, Any]) -> tuple[str, str]:
    repository = str(root.get("repository") or (root.get("context") or {}).get("repository") or "")
    owner, separator, repo = repository.partition("/")
    if not separator or not owner or not repo or "/" in repo:
        raise ValueError("bootstrap root repository must be owner/repository")
    return owner, repo


def _installation_id(root: dict[str, Any]) -> str:
    return str(root.get("installation_id") or (root.get("context") or {}).get("installation_id") or "")


def _source_issue_number(root: dict[str, Any]) -> int | None:
    """Return the optional GitHub issue status target for either schema."""
    if root.get("schema_version") == 1:
        return root.get("root_issue_number") if type(root.get("root_issue_number")) is int else None
    source = root.get("source")
    if not isinstance(source, dict) or source.get("kind") != "github-issue":
        return None
    if "issue-comment" not in source.get("projection_capabilities", []):
        return None
    value = source.get("issue_number")
    return value if type(value) is int and value > 0 else None


def _run_label(root: dict[str, Any]) -> str:
    return "Documentation bootstrap" if root.get("schema_version") == 1 else "Documentation journey"


def project_configured_root(state_dir: pathlib.Path | str, identity: str) -> dict[str, Any]:
    """Production caller for one persisted root using configured App identity."""
    config = common.load_effective_config()
    app = config.get("app")
    if not isinstance(app, dict):
        raise ValueError("GitHub App configuration is required for bootstrap projection")
    store = FileBootstrapStore(state_dir)
    with store.lock(identity):
        root = store.load(identity)
        if root is None:
            raise ValueError("bootstrap root was not found")

        # A terminal transition always wins over an outstanding projection.
        # In particular, do not let a previously persisted external action
        # escape a later cancellation, deadline, review, or budget limit.
        now = time.time()
        if root["state"] in TERMINAL_STATES:
            terminal_status_ids = {
                str(action["id"]) for action in root["actions"]
                if action.get("state") == "pending"
                and action.get("kind") == "post_root_status"
                and action.get("root_state") == root["state"]
            }
            if terminal_status_ids:
                try:
                    return project_actions(
                        root, GitHubCityBootstrapAdapter(app), persist=store.save,
                        pending_action_ids=terminal_status_ids,
                    )
                except Exception:
                    return store.save(root)
            return store.save(root)
        # An admitted child may legitimately consume the final child/PR
        # budget. Its persisted lifecycle intent must still settle before
        # capacity exhaustion is reconciled.
        terminal_state = _forced_terminal(root, now) if _pending(root) else _reconcile_terminal(root, now)
        if terminal_state is not None:
            terminal_root, status_action = _terminal(_copy_root(root), terminal_state)
            # The terminal transition itself is durable before its status may
            # be sent.  Its old active-work intents remain deliberately
            # excluded from this terminal-only projection.
            store.save(terminal_root)
            try:
                return project_actions(
                    terminal_root, GitHubCityBootstrapAdapter(app), persist=store.save,
                    pending_action_ids={str(status_action["id"])},
                )
            except Exception:
                return store.save(terminal_root)

        # Persisted staged successors are normal progress and project without
        # consuming the retry budget.  Conversely, a failed adapter attempt
        # leaves the action pending; reconcile it durably so repeated calls
        # are bounded by the root's non-progress budget.
        if _pending(root):
            try:
                return project_actions(root, GitHubCityBootstrapAdapter(app), persist=store.save)
            except Exception:
                retried, _ = reconcile_root(root, now=now)
                return store.save(retried)
        reconciled, _ = reconcile_root(root, now=time.time())
        return store.save(reconciled)


# v2 names are the public controller surface.  Keep the v1 names above as
# compatibility reads for persisted records and existing command wrappers.
FileJourneyStore = FileBootstrapStore
GitHubCityJourneyAdapter = GitHubCityBootstrapAdapter


def project_persisted_journey(store: FileJourneyStore, identity: str, adapter: Any) -> dict[str, Any]:
    return project_persisted_root(store, identity, adapter)


def project_configured_journey(state_dir: pathlib.Path | str, identity: str) -> dict[str, Any]:
    return project_configured_root(state_dir, identity)


def _project_action(root: dict[str, Any], action: dict[str, Any], adapter: Any) -> None:
    kind = action.get("kind")
    child = _action_child(root, action)
    if kind == "create_debt_issue":
        debt = _action_debt(root, action)
        resource = adapter.create_debt_issue(root, action, debt)
        _complete_action(action, resource)
        return
    if kind == "create_issue":
        resource = adapter.create_issue(root, action, child)
        _complete_action(action, resource)
        assert child is not None
        _append_action(root, _action(_child_action_id(child, "create_bead"), "create_bead", child_key=child["key"]))
        return
    if kind == "create_bead":
        resource = adapter.create_bead(root, action, child)
        _complete_action(action, resource)
        assert child is not None
        _append_action(root, _action(_child_action_id(child, "assign_bead"), "assign_bead", child_key=child["key"]))
        return
    if kind == "assign_bead":
        resource = adapter.assign_bead(root, action, child)
        _complete_action(action, resource)
        return
    if kind == "post_root_status":
        resource = adapter.post_root_status(root, action)
        _complete_action(action, resource)
        return
    if kind == "create_docs_pr":
        resource = adapter.create_docs_pr(root, action, child)
        _complete_action(action, resource)
        return
    raise ValueError(f"unsupported bootstrap projection action: {kind!r}")


def _action_child(root: dict[str, Any], action: dict[str, Any]) -> dict[str, Any] | None:
    key = action.get("child_key")
    if key is None:
        return None
    child = next((item for item in root["children"] if item.get("key") == key), None)
    if child is None:
        raise ValueError(f"bootstrap action references missing child: {key!r}")
    return child


def _action_debt(root: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    if root.get("schema_version") == 3:
        key = action.get("bud_identity")
        bud = next((item for item in root["buds"] if item.get("identity") == key), None)
        if bud is None:
            raise ValueError(f"recursion action references missing bud: {key!r}")
        return {"key": bud["identity"], "evidence_paths": bud["evidence_paths"],
                "coverage_cell": bud["decision_identity"].get("coverage_cell"),
                "decision_identity": copy.deepcopy(bud["decision_identity"])}
    key = action.get("debt_key")
    debt = next((item for item in root["debts"] if item.get("key") == key), None)
    if debt is None:
        raise ValueError(f"bootstrap action references missing debt: {key!r}")
    return debt


def _complete_action(action: dict[str, Any], resource: Any) -> None:
    if not isinstance(resource, dict):
        raise ValueError("bootstrap projection adapter must return a resource object")
    action["resource"] = copy.deepcopy(resource)
    action["state"] = "completed"


def _append_action(root: dict[str, Any], action: dict[str, Any]) -> None:
    if not any(existing.get("id") == action["id"] for existing in root["actions"]):
        root["actions"].append(action)


def _child_action_id(child: dict[str, Any], suffix: str) -> str:
    return f"{_child_action_prefix(child)}-child:{child['key']}:{suffix}"


def _action_prefix(root: dict[str, Any]) -> str:
    return "bootstrap" if root.get("schema_version") == 1 else "docs-journey"


def _child_action_prefix(child: dict[str, Any]) -> str:
    return "bootstrap" if "bootstrap_identity" in child else "docs-journey"


def _pending(root: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(action) for action in root["actions"] if action.get("state") == "pending"]


def _action(action_id: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {"id": action_id, "kind": kind, "state": "pending", **fields}


def _copy_root(root: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(root, dict) or root.get("state") not in {"active", *TERMINAL_STATES}:
        raise ValueError("root is invalid")
    result = copy.deepcopy(root)
    schema_version = result.get("schema_version")
    if schema_version not in {1, 2, 3}:
        raise ValueError("journey schema version is invalid")
    if schema_version == 1:
        _required_text(result, "root_issue_url")
        root_issue_number = result.get("root_issue_number")
        if type(root_issue_number) is not int or root_issue_number <= 0:
            raise ValueError("root_issue_number must be a positive integer")
    elif schema_version == 2:
        result["source"] = _source(result.get("source"))
        result["docs_impact_source_key"] = _required_text(result, "docs_impact_source_key")
    else:
        result["context"] = _context(result.get("context"))
        result["persona_goal_path"] = _persona_goal_path(result.get("persona_goal_path"))
        result["execution_budgets"] = _recursion_budgets(result.get("execution_budgets"))
        result["coverage_cells"] = _coverage_cells(result.get("coverage_cells"))
        for key in ("children", "buds", "coverage_results", "actions", "visited_surfaces"):
            if not isinstance(result.get(key), list):
                raise ValueError(f"root {key} must be a list")
        for key in ("children_used", "docs_prs_used", "non_progress_count"):
            if type(result.get(key)) is not int or result[key] < 0:
                raise ValueError(f"root {key} must be a non-negative integer")
        return result
    for key in ("children", "debts", "actions", "visited_surfaces"):
        if not isinstance(result.get(key), list):
            raise ValueError(f"root {key} must be a list")
    result["budgets"] = _validate_budgets(result.get("budgets"))
    result["journey"] = _journey(result.get("journey"))
    for key in ("children_used", "docs_prs_used", "debt_issues_used", "non_progress_count"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError(f"root {key} must be a non-negative integer")
    return result


def _repository_id(root: dict[str, Any]) -> str:
    return root["context"]["repository_id"] if root.get("schema_version") == 3 else root["repository_id"]


def _repository(root: dict[str, Any]) -> str:
    return root["context"]["repository"] if root.get("schema_version") == 3 else root["repository"]


def _snapshot_sha(root: dict[str, Any]) -> str:
    return root["context"]["default_branch_sha"] if root.get("schema_version") == 3 else root["default_branch_sha"]


def _execution_budgets(root: dict[str, Any]) -> dict[str, int]:
    return root["execution_budgets"] if root.get("schema_version") == 3 else root["budgets"]


def _context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("context is required")
    result = {key: _required_text(value, key) for key in ("kind", "key", "url", "repository_id", "repository", "installation_id", "docs_impact_source_key", "default_branch")}
    if result["kind"] not in {"github-pr", "github-issue", "operator-request"}:
        raise ValueError("context kind is unsupported")
    result["default_branch_sha"] = _sha(value.get("default_branch_sha"), "context default_branch_sha")
    capabilities = value.get("projection_capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(item, str) or not item.strip() for item in capabilities):
        raise ValueError("context projection_capabilities must be a list of text")
    result["projection_capabilities"] = sorted(set(capabilities))
    return result


def _persona_goal_path(value: Any) -> dict[str, list[dict[str, str]]]:
    """Normalize the declared ordered paths without choosing a winner."""
    raw_paths = value.get("paths") if isinstance(value, dict) and set(value) == {"paths"} else value
    if isinstance(raw_paths, dict):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("persona_goal_path is required")
    paths: list[dict[str, str]] = []
    for item in raw_paths:
        if not isinstance(item, dict):
            raise ValueError("persona_goal_path entries must be objects")
        result = {key: _required_text(item, key) for key in ("domain", "role", "job", "starting_context", "success_condition", "documentation_entry_point")}
        if result["domain"] != "techdocs":
            raise ValueError("persona_goal_path domain must be techdocs")
        result["documentation_entry_point"] = select_documentation_root({"documentation_index": result["documentation_entry_point"]})
        paths.append(result)
    return {"paths": paths}


def _recursion_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("budgets must be an object")
    fields = ("max_depth", "max_children", "max_docs_prs", "max_elapsed_seconds", "max_non_progress")
    result: dict[str, int] = {}
    for key in fields:
        item = value.get(key)
        if type(item) is not int or item <= 0:
            raise ValueError(f"budget {key} must be a positive integer")
        result[key] = item
    return result


def _coverage_cells(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("coverage_cells must be a non-empty ordered list")
    cells: list[dict[str, str]] = []
    for item in value:
        identity = item if isinstance(item, str) else item.get("identity") if isinstance(item, dict) else None
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("coverage cell identity must be non-empty text")
        cells.append({"identity": identity.strip()})
    if len({item["identity"] for item in cells}) != len(cells):
        raise ValueError("coverage cell identities must be unique")
    return cells


def _source(value: Any) -> dict[str, Any]:
    """Validate provenance supplied by a source adapter, without privileging it."""
    if not isinstance(value, dict):
        raise ValueError("journey source is required")
    result: dict[str, Any] = {
        "kind": _required_text(value, "kind"),
        "key": _required_text(value, "key"),
        "url": _required_text(value, "url"),
    }
    capabilities = value.get("projection_capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(item, str) or not item.strip() for item in capabilities):
        raise ValueError("source projection_capabilities must be a list of text")
    result["projection_capabilities"] = sorted(set(capabilities))
    issue_number = value.get("issue_number")
    if issue_number is not None:
        if type(issue_number) is not int or issue_number <= 0:
            raise ValueError("source issue_number must be a positive integer")
        result["issue_number"] = issue_number
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


def _journey(value: Any) -> dict[str, str]:
    """Validate the fixed reader journey without inferring any of its content."""
    if not isinstance(value, dict):
        raise ValueError("reader journey is required")
    domain = _required_text(value, "domain")
    if domain != "techdocs":
        raise ValueError("domain must be techdocs")
    result = {
        "domain": domain,
        "role": _required_text(value, "role"),
        "job": _required_text(value, "job"),
        "starting_context": _required_text(value, "starting_context"),
        "success_condition": _required_text(value, "success_condition"),
        "backfill_policy": _required_text(value, "backfill_policy"),
    }
    if result["backfill_policy"] not in {"blocking-only", "record-debt"}:
        raise ValueError("backfill_policy is unsupported")
    return result


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
