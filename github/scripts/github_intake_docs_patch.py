#!/usr/bin/env python3
"""Validate and canonically serialize revision-bound documentation patch proposals."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
from typing import Any

SCHEMA_VERSION = 1
MAX_DIFF_BYTES = 64 * 1024
MAX_FILES = 32
MAX_CLAIMS = 64
MAX_CHECKS = 16

DOCUMENTATION_PREFIXES = ("docs/", "doc/", "documentation/")
DOCUMENTATION_FILENAMES = {"readme.md", "changelog.md", "contributing.md"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIFF_PATH_PATTERN = re.compile(r"^diff --git a/(.+) b/(.+)$", re.MULTILINE)
RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)\b(x-auth-token|private[-_ ]?key|client[-_ ]?secret)\s*[:=]\s*[^\s]+"),
)

ROOT_FIELDS = {
    "schema_version", "status", "generated_at", "identity", "patch_sha256", "diff", "files", "claims", "checks",
}
IDENTITY_FIELDS = {
    "repository_id", "repository", "pr_number", "base_sha", "head_sha", "head_repository_id", "head_repository", "base_ref",
}
FILE_FIELDS = {"path", "sha256"}
CLAIM_FIELDS = {"claim", "evidence", "release_scope"}
CHECK_FIELDS = {"command", "status", "explanation"}
ROOT_FIELDS_WITH_DIGEST = ROOT_FIELDS | {"artifact_sha256"}


def canonical_json(value: dict[str, Any]) -> str:
    """Render JSON deterministically for storage, digesting, and safe projection."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _expect_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _expect_fields(value: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ValueError(f"{field} fields invalid; missing={missing}, unexpected={unknown}")


def _text(value: Any, field: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value


def _redact(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda match: match.group(1) + "[REDACTED]" if match.lastindex else "[REDACTED]", value)
    return value


def _validate_path(path: str) -> str:
    if "\\" in path or path.startswith("/") or path in {".", ".."}:
        raise ValueError(f"unsafe documentation path: {path!r}")
    parts = pathlib.PurePosixPath(path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe documentation path: {path!r}")
    lowered = path.lower()
    if not lowered.startswith(DOCUMENTATION_PREFIXES) and pathlib.PurePosixPath(lowered).name not in DOCUMENTATION_FILENAMES:
        raise ValueError(f"non-documentation path: {path!r}")
    return path


def _validate_identity(identity: Any) -> dict[str, Any]:
    identity = _expect_object(identity, "identity")
    _expect_fields(identity, IDENTITY_FIELDS, "identity")
    normalized = copy.deepcopy(identity)
    for field in ("repository_id", "repository", "head_repository_id", "head_repository", "base_ref"):
        normalized[field] = _text(normalized[field], f"identity.{field}", 256)
    if not isinstance(normalized["pr_number"], int) or normalized["pr_number"] <= 0:
        raise ValueError("identity.pr_number must be a positive integer")
    for field in ("base_sha", "head_sha"):
        value = _text(normalized[field], f"identity.{field}", 40).lower()
        if not GIT_SHA_PATTERN.fullmatch(value):
            raise ValueError(f"identity.{field} must be a 40-character lowercase Git SHA")
        normalized[field] = value
    return normalized


def _validate_diff(diff: Any, patch_sha256: str, files: list[dict[str, Any]]) -> str:
    diff = _text(diff, "diff", MAX_DIFF_BYTES * 2)
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise ValueError("diff is too large")
    if "\x00" in diff or "GIT binary patch" in diff or "Binary files " in diff:
        raise ValueError("binary diff is not allowed")
    if "new file mode 120000" in diff or "old mode 120000" in diff:
        raise ValueError("symlink diff is not allowed")
    if any(pattern.search(diff) for pattern in SECRET_PATTERNS):
        raise ValueError("diff contains a secret")
    actual = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    if actual != patch_sha256:
        raise ValueError("patch_sha256 does not match diff")
    diff_paths: set[str] = set()
    for old_path, new_path in DIFF_PATH_PATTERN.findall(diff):
        if old_path != "/dev/null":
            diff_paths.add(_validate_path(old_path))
        if new_path != "/dev/null":
            diff_paths.add(_validate_path(new_path))
    if not diff_paths:
        raise ValueError("diff must contain a unified documentation patch")
    file_paths = {file["path"] for file in files}
    if diff_paths != file_paths:
        raise ValueError("diff paths must exactly match files paths")
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = line.removeprefix("--- ")
            if path != "/dev/null":
                if not path.startswith("a/"):
                    raise ValueError(f"unsafe unified diff path: {path!r}")
                path = _validate_path(path.removeprefix("a/"))
                if path not in file_paths:
                    raise ValueError("unified diff paths must exactly match files paths")
        elif line.startswith("+++ "):
            path = line.removeprefix("+++ ")
            if path != "/dev/null":
                if not path.startswith("b/"):
                    raise ValueError(f"unsafe unified diff path: {path!r}")
                path = _validate_path(path.removeprefix("b/"))
                if path not in file_paths:
                    raise ValueError("unified diff paths must exactly match files paths")
    return diff


def _validate_files(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > MAX_FILES:
        raise ValueError("files must be a non-empty bounded list")
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item = _expect_object(item, f"files[{index}]")
        _expect_fields(item, FILE_FIELDS, f"files[{index}]")
        path = _validate_path(_text(item["path"], f"files[{index}].path", 1024))
        digest = _text(item["sha256"], f"files[{index}].sha256", 64).lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"files[{index}].sha256 must be a SHA-256 digest")
        if path in seen:
            raise ValueError("files paths must be unique")
        seen.add(path)
        files.append({"path": path, "sha256": digest})
    return sorted(files, key=lambda item: item["path"])


def _validate_claims(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > MAX_CLAIMS:
        raise ValueError("claims must be a non-empty bounded list")
    claims: list[dict[str, str]] = []
    for index, item in enumerate(value):
        item = _expect_object(item, f"claims[{index}]")
        _expect_fields(item, CLAIM_FIELDS, f"claims[{index}]")
        evidence = _text(item["evidence"], f"claims[{index}].evidence", 2048)
        if not (evidence.startswith("github://") or evidence.startswith("https://") or evidence.startswith("git:")):
            raise ValueError(f"claims[{index}].evidence must be an immutable evidence reference")
        git_sha = re.search(r"\b[0-9a-f]{40}\b", evidence)
        if evidence.startswith("git:") and git_sha is None:
            raise ValueError(f"claims[{index}].evidence must pin a commit SHA")
        if not evidence.startswith("git:") and re.search(r"/(?:blob|commit)/[0-9a-f]{40}(?:/|$)", evidence) is None:
            raise ValueError(f"claims[{index}].evidence must pin a commit SHA")
        claims.append({
            "claim": _redact(_text(item["claim"], f"claims[{index}].claim", 4096)),
            "evidence": _redact(evidence),
            "release_scope": _redact(_text(item["release_scope"], f"claims[{index}].release_scope", 512)),
        })
    return sorted(claims, key=lambda item: (item["claim"], item["evidence"], item["release_scope"]))


def _validate_checks(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > MAX_CHECKS:
        raise ValueError("checks must be a non-empty bounded list")
    checks: list[dict[str, str]] = []
    for index, item in enumerate(value):
        item = _expect_object(item, f"checks[{index}]")
        _expect_fields(item, CHECK_FIELDS, f"checks[{index}]")
        status = _text(item["status"], f"checks[{index}].status", 16)
        if status not in {"passed", "failed", "unavailable"}:
            raise ValueError(f"checks[{index}].status must be passed, failed, or unavailable")
        checks.append({
            "command": _redact(_text(item["command"], f"checks[{index}].command", 2048)),
            "status": status,
            "explanation": _redact(_text(item["explanation"], f"checks[{index}].explanation", 4096)),
        })
    return sorted(checks, key=lambda item: (item["command"], item["status"], item["explanation"]))


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical, redacted artifact or raise ValueError for unsafe input."""
    value = _expect_object(value, "artifact")
    if set(value) != ROOT_FIELDS and set(value) != ROOT_FIELDS_WITH_DIGEST:
        _expect_fields(value, ROOT_FIELDS, "artifact")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if value["status"] not in {"proposed", "unavailable", "unsafe"}:
        raise ValueError("status must be proposed, unavailable, or unsafe")
    generated_at = _text(value["generated_at"], "generated_at", 64)
    if RFC3339_PATTERN.fullmatch(generated_at) is None:
        raise ValueError("generated_at must be RFC3339 with a timezone")
    try:
        parsed_time = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("generated_at must be RFC3339") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise ValueError("generated_at must be RFC3339 with a timezone")
    patch_sha256 = _text(value["patch_sha256"], "patch_sha256", 64).lower()
    if not SHA256_PATTERN.fullmatch(patch_sha256):
        raise ValueError("patch_sha256 must be a SHA-256 digest")
    files = _validate_files(value["files"])
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "status": value["status"],
        "generated_at": generated_at,
        "identity": _validate_identity(value["identity"]),
        "patch_sha256": patch_sha256,
        "diff": _validate_diff(value["diff"], patch_sha256, files),
        "files": files,
        "claims": _validate_claims(value["claims"]),
        "checks": _validate_checks(value["checks"]),
    }
    artifact_sha256 = hashlib.sha256(canonical_json(artifact).encode("utf-8")).hexdigest()
    supplied_digest = value.get("artifact_sha256")
    if supplied_digest is not None:
        supplied_digest = _text(supplied_digest, "artifact_sha256", 64).lower()
        if not SHA256_PATTERN.fullmatch(supplied_digest) or supplied_digest != artifact_sha256:
            raise ValueError("artifact_sha256 does not match canonical artifact")
    artifact["artifact_sha256"] = artifact_sha256
    return artifact
