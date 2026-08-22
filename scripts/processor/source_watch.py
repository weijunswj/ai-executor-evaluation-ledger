"""Strict Source Watch envelope parsing and fail-closed planning."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from scripts.processor.common import (
    reject_duplicate_json_keys,
    valid_sha256,
    valid_git_sha,
    valid_identifier,
)

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
        metadata = json.loads(
            json_text,
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_constant,
        )
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
        "dry_run",
    }
    allowed = required | {
        "review_freeze_state",
        "source_authority_mode",
        "router_issue_number",
        "router_revision",
        "source_generation",
        "source_watermark",
        "source_snapshot_sha256",
    }
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
    if (
        "review_freeze_state" in metadata
        and metadata["review_freeze_state"] not in {"not_started", "frozen"}
    ):
        raise ValueError("invalid_source_watch_metadata")


    router_fields = {
        "source_authority_mode",
        "router_issue_number",
        "router_revision",
        "source_generation",
        "source_watermark",
        "source_snapshot_sha256",
    }
    if router_fields & set(metadata):
        if (
            metadata.get("source_authority_mode") != "router_v1"
            or router_fields - set(metadata)
            or metadata.get("router_issue_number") != 142
            or not isinstance(metadata.get("router_revision"), int)
            or isinstance(metadata.get("router_revision"), bool)
            or metadata.get("router_revision") <= 0
            or not isinstance(metadata.get("source_generation"), int)
            or isinstance(metadata.get("source_generation"), bool)
            or metadata.get("source_generation") < 0
            or not isinstance(metadata.get("source_watermark"), int)
            or isinstance(metadata.get("source_watermark"), bool)
            or metadata.get("source_watermark") < 0
            or not valid_sha256(metadata.get("source_snapshot_sha256"))
            or (metadata.get("source_generation") == 0 and metadata.get("source_issue_number") != 142)
            or (metadata.get("source_generation") > 0 and metadata.get("source_issue_number") == 142)
        ):
            raise ValueError("invalid_source_watch_metadata")
def stale_route_report(
    *,
    router_revision: int,
    source_generation: int,
    source_issue_number: int,
    source_watermark: int,
    comment_id: int,
    ) -> Dict[str, Any]:
    if (
        not isinstance(router_revision, int)
        or isinstance(router_revision, bool)
        or router_revision <= 0
        or not isinstance(source_generation, int)
        or isinstance(source_generation, bool)
        or source_generation < 0
        or not isinstance(source_issue_number, int)
        or isinstance(source_issue_number, bool)
        or source_issue_number <= 0
        or not isinstance(source_watermark, int)
        or isinstance(source_watermark, bool)
        or source_watermark < 0
        or not isinstance(comment_id, int)
        or isinstance(comment_id, bool)
        or comment_id <= 0
    ):
        raise ValueError("invalid_stale_route_report")
    if comment_id <= source_watermark:
        raise ValueError("not_stale_route")
    return {
        "classification": "stale_route",
        "router_revision": router_revision,
        "source_generation": source_generation,
        "source_issue_number": source_issue_number,
        "source_watermark": source_watermark,
        "queued": False,
        "pending": False,
        "recorded": False,
        "processor_receipt": False,
        "canonical": False,
        "source_excluded": True,
        "retained": True,
        "auditable": True,
        "disposition_required": False,
        "authority": "router_revision_plus_retired_segment_boundary",
    }
def _complete_connection_nodes(value: Any) -> Optional[list[Any]]:
    """Validate one fully aggregated native GraphQL connection."""

    if not isinstance(value, dict) or set(value) != {
        "nodes",
        "pageInfo",
        "totalCount",
    }:
        return None
    nodes = value.get("nodes")
    page_info = value.get("pageInfo")
    total_count = value.get("totalCount")
    if (
        not isinstance(nodes, list)
        or not isinstance(page_info, dict)
        or "hasNextPage" not in page_info
        or set(page_info)
        - {
            "hasNextPage",
            "hasPreviousPage",
            "startCursor",
            "endCursor",
        }
        or not isinstance(page_info.get("hasNextPage"), bool)
        or page_info["hasNextPage"]
        or not isinstance(total_count, int)
        or isinstance(total_count, bool)
        or total_count != len(nodes)
    ):
        return None
    if (
        "hasPreviousPage" in page_info
        and not isinstance(page_info["hasPreviousPage"], bool)
    ):
        return None
    for field in ("startCursor", "endCursor"):
        if field in page_info and not (
            page_info[field] is None
            or isinstance(page_info[field], str)
        ):
            return None
    return nodes


def normalize_native_review_evidence(
    pr_meta: Dict[str, Any],
) -> Optional[Dict[str, list[Any]]]:
    """Convert closed native connections into the internal review DTO."""

    normalized: Dict[str, list[Any]] = {}
    for field in ("reviews", "latestReviews", "reviewThreads"):
        if field not in pr_meta:
            return None
        nodes = _complete_connection_nodes(pr_meta[field])
        if nodes is None:
            return None
        normalized[field] = nodes
    return normalized


def _native_review_activity(pr_meta: Dict[str, Any]) -> Optional[bool]:
    """Return explicit review activity, or ``None`` for ambiguous evidence."""

    normalized = normalize_native_review_evidence(pr_meta)
    if normalized is None:
        return None
    activity = any(normalized.values())
    controller_started = pr_meta.get("controller_review_started")
    if controller_started is not None:
        if not isinstance(controller_started, bool):
            return None
        activity = activity or controller_started
    return activity


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
        freeze_state = parsed_meta.get("review_freeze_state")
        expected_head = parsed_meta.get("expected_head_sha")
        if freeze_state == "frozen" and expected_head != current_head_sha:
            return {"action": "REFUSE_FROZEN", "reason": "frozen_head_mismatch"}
        if freeze_state == "frozen":
            return {"action": "REFUSE_FROZEN", "reason": "review_freeze"}
        if expected_head and expected_head != current_head_sha:
            return {"action": "REFUSE_UNEXPECTED_HEAD", "reason": "expected_head_mismatch"}
        native_review_activity = _native_review_activity(pr_meta)
        if native_review_activity is None:
            return {"action": "REFUSE_AMBIGUOUS_OWNERSHIP", "reason": "ambiguous_review_state"}
        if native_review_activity and freeze_state is None:
            return {"action": "REFUSE_FROZEN", "reason": "review_freeze_missing"}
        if native_review_activity and freeze_state != "frozen":
            return {"action": "REFUSE_FROZEN", "reason": "review_freeze_conflict"}
        if native_review_activity:
            return {"action": "REFUSE_FROZEN", "reason": "review_freeze"}
        return {
            "action": "UPDATE_EXISTING_PR",
            "pr_number": pr_meta.get("number"),
            "reason": "safe_mutable_source_watch_pr",
        }
