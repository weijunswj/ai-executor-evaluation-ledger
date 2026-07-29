"""Strict Source Watch envelope parsing and fail-closed planning."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from scripts.processor.common import valid_git_sha, valid_identifier

OWNERSHIP_MARKER = "<!-- ledger-source-watch:v1 -->"
METADATA_RECORD_TYPE = "source_watch_pr_metadata"


def _safe_invalid() -> ValueError:
    return ValueError("invalid_source_watch_envelope")


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


def parse_pr_body(body: str) -> Tuple[Dict[str, Any], str]:
    """Parse one byte-zero marker and one closed fenced JSON object."""

    if not isinstance(body, str) or not body.startswith(OWNERSHIP_MARKER):
        raise _safe_invalid()

    rest = body[len(OWNERSHIP_MARKER) :].lstrip("\r\n")
    opening = None
    if rest.startswith("```json\r\n"):
        opening = "```json\r\n"
    elif rest.startswith("```json\n"):
        opening = "```json\n"
    elif rest.startswith("```\r\n"):
        opening = "```\r\n"
    elif rest.startswith("```\n"):
        opening = "```\n"
    if opening is None:
        raise _safe_invalid()

    content = rest[len(opening) :]
    lines = content.splitlines(keepends=True)
    close_start = None
    close_length = None
    payload_lines = []
    consumed = 0
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped == "```":
            close_start = consumed
            close_length = len(line)
            break
        payload_lines.append(line)
        consumed += len(line)
    if close_start is None or close_length is None:
        raise _safe_invalid()

    json_text = "".join(payload_lines).strip()
    try:
        metadata = json.loads(json_text, parse_constant=_reject_nonfinite_constant)
    except (TypeError, ValueError):
        raise _safe_invalid()
    if not isinstance(metadata, dict):
        raise _safe_invalid()

    remaining_body = content[close_start + close_length :].lstrip("\r\n")
    if OWNERSHIP_MARKER in remaining_body or METADATA_RECORD_TYPE in remaining_body:
        raise _safe_invalid()
    return metadata, remaining_body


def validate_metadata(metadata: Dict[str, Any]) -> None:
    """Validate the closed metadata contract without echoing source values."""

    required = {
        "schema_version",
        "record_type",
        "mode",
        "base_sha",
        "canonical_main_sha",
        "batch_id",
        "controller_run_id",
        "pr_number",
        "expected_head_sha",
        "activation_mode",
        "source_issue_number",
        "receipt_issue_number",
        "review_freeze_state",
        "dry_run",
    }
    allowed = required | {"review_freeze_state", "dry_run"}
    if set(metadata) - allowed or not required.issubset(metadata):
        raise ValueError("invalid_source_watch_metadata")
    if metadata["schema_version"] != 1 or metadata["record_type"] != METADATA_RECORD_TYPE:
        raise ValueError("invalid_source_watch_metadata")
    if metadata["mode"] not in {"initial", "incremental"}:
        raise ValueError("invalid_source_watch_metadata")
    for field in ("base_sha", "canonical_main_sha", "expected_head_sha"):
        if not valid_git_sha(metadata[field]):
            raise ValueError("invalid_source_watch_metadata")
    for field in ("batch_id", "controller_run_id"):
        if not valid_identifier(metadata[field]):
            raise ValueError("invalid_source_watch_metadata")
    if not isinstance(metadata["pr_number"], int) or metadata["pr_number"] <= 0:
        raise ValueError("invalid_source_watch_metadata")
    if not isinstance(metadata["source_issue_number"], int) or metadata["source_issue_number"] <= 0:
        raise ValueError("invalid_source_watch_metadata")
    if not isinstance(metadata["receipt_issue_number"], int) or metadata["receipt_issue_number"] <= 0:
        raise ValueError("invalid_source_watch_metadata")
    if metadata["activation_mode"] not in {"dry-run", "reviewed-live"}:
        raise ValueError("invalid_source_watch_metadata")
    if metadata["activation_mode"] == "dry-run" and metadata["dry_run"] is not True:
        raise ValueError("invalid_source_watch_metadata")
    if metadata["activation_mode"] == "reviewed-live" and metadata["dry_run"] is not False:
        raise ValueError("invalid_source_watch_metadata")
    if metadata["review_freeze_state"] not in {"not_started", "frozen"}:
        raise ValueError("invalid_source_watch_metadata")


class SourceWatchPlanner:
    """Deterministic planner that performs no network or credential operation."""

    OWNERSHIP_MARKER = OWNERSHIP_MARKER

    def plan_pr_action(
        self,
        pr_meta: Optional[Dict[str, Any]],
        has_pending_work: bool,
        current_head_sha: str,
    ) -> Dict[str, Any]:
        if not has_pending_work:
            return {"action": "NO_WORK", "reason": "no_work"}
        if pr_meta is None:
            return {"action": "CREATE_NEW_DRAFT_PR", "reason": "no_active_source_watch_pr"}

        try:
            parsed_meta, _ = parse_pr_body(pr_meta.get("body", ""))
            validate_metadata(parsed_meta)
        except ValueError:
            return {"action": "REFUSE_AMBIGUOUS_OWNERSHIP", "reason": "invalid_source_watch_envelope"}
        if pr_meta.get("number") != parsed_meta["pr_number"]:
            return {"action": "REFUSE_AMBIGUOUS_OWNERSHIP", "reason": "pr_number_mismatch"}
        if not pr_meta.get("is_draft", False):
            return {"action": "REFUSE_NOT_DRAFT", "reason": "pr_not_draft"}
        if pr_meta.get("is_frozen", False) or parsed_meta.get("review_freeze_state") == "frozen":
            return {"action": "REFUSE_FROZEN", "reason": "review_freeze"}
        expected_head = parsed_meta.get("expected_head_sha") or parsed_meta.get("final_expected_head")
        if expected_head and expected_head != current_head_sha:
            return {"action": "REFUSE_UNEXPECTED_HEAD", "reason": "expected_head_mismatch"}
        return {
            "action": "UPDATE_EXISTING_PR",
            "pr_number": pr_meta.get("number"),
            "reason": "safe_mutable_source_watch_pr",
        }
