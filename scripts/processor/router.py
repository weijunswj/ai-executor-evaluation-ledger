"""Fail-closed parsing and authority checks for the ledger intake router.

The router is the source of routing authority. GitHub lock state, comment body
status text, and a successful API write are observations only; none can extend
a committed legacy boundary or make an intake canonical.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional

import jsonschema


MARKER = "<!-- ledger-routing:v1 -->"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "routing.schema.json"
ROUTER_STATES = frozenset(
    {
        "LEGACY_ACTIVE",
        "PREPARED",
        "CUTOVER_COMMITTED",
        "SUCCESSOR_ACTIVE",
        "MIGRATION_VERIFIED",
    }
)
ACTIVE_STATES = frozenset({"LEGACY_ACTIVE", "SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"})
COMMITTED_STATES = frozenset({"CUTOVER_COMMITTED", "SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"})


class RouterValidationError(ValueError):
    """Raised for an invalid router, anchor, transition, or source binding."""


def _reject_constant(value: str) -> None:
    raise RouterValidationError(f"nonfinite_json_number:{value}")


def _duplicate_rejecting_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RouterValidationError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _json_loads(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_duplicate_rejecting_pairs, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RouterValidationError, ValueError) as error:
        raise RouterValidationError("router_json_invalid") from error


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def router_body_sha256(router: Mapping[str, Any]) -> str:
    """Hash the canonical router/anchor object represented after the marker."""

    return hashlib.sha256(_canonical_json_bytes(router)).hexdigest()


def cutover_anchor_sha256(anchor: Mapping[str, Any]) -> str:
    """Hash the immutable anchor's canonical object bytes."""

    return router_body_sha256(anchor)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RouterValidationError(code)


def _is_int(value: Any, *, positive: bool = False) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and (value > 0 if positive else value >= 0)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _load_schema() -> dict[str, Any]:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouterValidationError("routing_schema_unavailable") from error


def _schema_validate(value: Mapping[str, Any]) -> None:
    schema = _load_schema()
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(dict(value))
    except (jsonschema.SchemaError, jsonschema.ValidationError) as error:
        raise RouterValidationError("router_schema_invalid") from error


def _validate_router_semantics(router: Mapping[str, Any]) -> dict[str, Any]:
    _schema_validate(router)
    value = dict(router)
    state = value["cutover_state"]
    legacy_generation = value["legacy_generation"]
    legacy_issue = value["legacy_issue_number"]
    active_generation = value["active_generation"]
    active_issue = value["active_issue_number"]
    predecessor_generation = value["predecessor_generation"]
    predecessor_issue = value["predecessor_issue_number"]
    successor_generation = value["successor_generation"]
    successor_issue = value["successor_issue_number"]
    final_watermark = value["final_watermark"]

    _require(value["router_revision"] > 0, "router_revision_invalid")
    _require(value["rotation_threshold"] == 500, "rotation_threshold_invalid")
    _require(legacy_generation == 0, "legacy_generation_must_be_zero")
    _require(legacy_issue > 0, "legacy_issue_invalid")

    if state == "LEGACY_ACTIVE":
        _require(active_generation == legacy_generation, "legacy_active_generation_invalid")
        _require(active_issue == legacy_issue, "legacy_active_issue_invalid")
        _require(value["legacy_segment_state"] == "active", "legacy_active_state_invalid")
        _require(final_watermark is None, "legacy_active_watermark_present")
        _require(value["cutover_anchor_sha256"] is None, "legacy_active_anchor_present")
        _require(
            predecessor_generation is None
            and predecessor_issue is None
            and successor_generation is None
            and successor_issue is None,
            "legacy_active_successor_present",
        )
    elif state == "PREPARED":
        _require(active_generation is None and active_issue is None, "prepared_active_target_present")
        _require(value["legacy_segment_state"] == "paused", "prepared_legacy_state_invalid")
        _require(final_watermark is None, "prepared_watermark_present")
        _require(value["cutover_anchor_sha256"] is None, "prepared_anchor_present")
        _require(
            predecessor_generation is None
            and predecessor_issue is None
            and successor_generation is None
            and successor_issue is None,
            "prepared_successor_present",
        )
    elif state == "CUTOVER_COMMITTED":
        _require(active_generation is None and active_issue is None, "committed_active_target_present")
        _require(value["legacy_segment_state"] == "frozen", "committed_legacy_state_invalid")
        _require(_is_int(final_watermark), "committed_watermark_invalid")
        _require(_is_sha256(value["cutover_anchor_sha256"]), "committed_anchor_invalid")
        _require(_is_int(predecessor_generation), "committed_predecessor_generation_invalid")
        _require(predecessor_generation == legacy_generation, "committed_predecessor_generation_mismatch")
        _require(predecessor_issue == legacy_issue, "committed_predecessor_issue_mismatch")
        _require(_is_int(successor_generation), "committed_successor_generation_invalid")
        _require(successor_generation == legacy_generation + 1, "committed_successor_generation_not_contiguous")
        _require(_is_int(successor_issue, positive=True), "committed_successor_issue_invalid")
        _require(successor_issue != legacy_issue, "committed_successor_issue_reused")
    elif state in {"SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"}:
        _require(_is_int(active_generation), "successor_active_generation_invalid")
        _require(_is_int(active_issue, positive=True), "successor_active_issue_invalid")
        _require(value["legacy_segment_state"] == "retired", "successor_legacy_state_invalid")
        _require(_is_int(final_watermark), "successor_watermark_invalid")
        _require(_is_sha256(value["cutover_anchor_sha256"]), "successor_anchor_invalid")
        _require(_is_int(predecessor_generation), "successor_predecessor_generation_invalid")
        _require(predecessor_generation == legacy_generation, "successor_predecessor_generation_mismatch")
        _require(predecessor_issue == legacy_issue, "successor_predecessor_issue_mismatch")
        _require(_is_int(successor_generation), "successor_generation_invalid")
        _require(successor_generation == legacy_generation + 1, "successor_generation_not_contiguous")
        _require(active_generation == successor_generation, "successor_active_generation_mismatch")
        _require(_is_int(successor_issue, positive=True), "successor_issue_invalid")
        _require(active_issue == successor_issue, "successor_active_issue_mismatch")
        _require(active_issue != legacy_issue, "successor_active_issue_reused")
    else:
        raise RouterValidationError("cutover_state_invalid")
    return value


def validate_router(router: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the closed schema plus cross-field authority invariants."""

    _require(isinstance(router, Mapping), "router_not_object")
    return _validate_router_semantics(router)


def parse_router_body(body: str) -> dict[str, Any]:
    """Parse exactly one byte-zero marker and one JSON object with LF ending."""

    _require(isinstance(body, str), "router_body_not_text")
    _require(body.startswith(MARKER + "\n"), "router_marker_not_at_byte_zero")
    payload = body[len(MARKER) + 1 :]
    _require(payload.endswith("\n"), "router_body_missing_terminal_lf")
    payload = payload[:-1]
    _require(payload and payload.strip() == payload, "router_body_whitespace_invalid")
    value = _json_loads(payload)
    _require(isinstance(value, dict), "router_payload_not_object")
    return validate_router(value)


def router_body_sha256_from_text(body: str) -> str:
    """Return the canonical object hash after parsing the complete body."""

    return router_body_sha256(parse_router_body(body))


def validate_router_transition(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    """Validate a monotonic observed router transition."""

    old = validate_router(previous)
    new = validate_router(current)
    _require(new["router_revision"] > old["router_revision"], "router_revision_not_monotonic")
    _require(new["legacy_generation"] == old["legacy_generation"], "legacy_generation_changed")
    _require(new["legacy_issue_number"] == old["legacy_issue_number"], "legacy_issue_changed")
    _require(new["rotation_threshold"] == old["rotation_threshold"], "rotation_threshold_changed")

    if old["final_watermark"] is not None:
        _require(new["final_watermark"] == old["final_watermark"], "final_watermark_advanced")
        _require(new["cutover_anchor_sha256"] == old["cutover_anchor_sha256"], "cutover_anchor_changed")
        _require(
            new["predecessor_generation"] == old["predecessor_generation"]
            and new["predecessor_issue_number"] == old["predecessor_issue_number"]
            and new["successor_generation"] == old["successor_generation"]
            and new["successor_issue_number"] == old["successor_issue_number"],
            "cutover_relation_changed",
        )

    allowed = {
        "LEGACY_ACTIVE": {"LEGACY_ACTIVE", "PREPARED"},
        "PREPARED": {"PREPARED", "LEGACY_ACTIVE", "CUTOVER_COMMITTED"},
        "CUTOVER_COMMITTED": {"CUTOVER_COMMITTED", "SUCCESSOR_ACTIVE"},
        "SUCCESSOR_ACTIVE": {"SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"},
        "MIGRATION_VERIFIED": {"MIGRATION_VERIFIED"},
    }
    _require(new["cutover_state"] in allowed[old["cutover_state"]], "router_state_transition_invalid")
    if old["cutover_state"] in COMMITTED_STATES:
        _require(
            new["cutover_state"] in {"CUTOVER_COMMITTED", "SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"},
            "cutover_rollback",
        )


def resolve_active_segment(router: Mapping[str, Any]) -> tuple[int, int, int]:
    """Return generation, issue, and threshold only for a postable state."""

    value = validate_router(router)
    _require(value["cutover_state"] in ACTIVE_STATES, "router_not_postable")
    return value["active_generation"], value["active_issue_number"], value["rotation_threshold"]


def validate_source_segment_binding(
    router: Mapping[str, Any],
    *,
    router_revision: int,
    source_generation: int,
    source_issue_number: int,
    source_watermark: int,
    source_snapshot_sha256: str,
) -> None:
    """Require every segment-aware batch to bind to the observed router."""

    value = validate_router(router)
    _require(value["cutover_state"] in ACTIVE_STATES, "router_not_postable")
    _require(router_revision == value["router_revision"], "router_revision_binding_mismatch")
    _require(source_generation == value["active_generation"], "source_generation_binding_mismatch")
    _require(source_issue_number == value["active_issue_number"], "source_issue_binding_mismatch")
    _require(source_issue_number == value["active_issue_number"], "source_issue_binding_mismatch")
    _require(_is_int(source_watermark), "source_watermark_invalid")
    _require(_is_sha256(source_snapshot_sha256), "source_snapshot_binding_invalid")


def validate_cutover_anchor(anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Validate future immutable-anchor schema; do not create an anchor."""

    _require(isinstance(anchor, Mapping), "cutover_anchor_not_object")
    _require(anchor.get("manifest_type") == "ledger_router_cutover_anchor", "cutover_anchor_type_invalid")
    _schema_validate(anchor)
    _require(anchor["successor_generation"] == anchor["legacy_generation"] + 1, "cutover_anchor_generation_invalid")
    _require(anchor["successor_issue_number"] != anchor["legacy_issue_number"], "cutover_anchor_issue_reused")
    _require(anchor["router_revision"] > 0, "cutover_anchor_revision_invalid")
    _require(anchor["final_watermark"] >= 0, "cutover_anchor_watermark_invalid")
    return dict(anchor)


def validate_cutover_anchor_binding(router: Mapping[str, Any], anchor: Mapping[str, Any]) -> None:
    """Ensure a future anchor describes the exact router cutover fields."""

    value = validate_router(router)
    bound = validate_cutover_anchor(anchor)
    _require(value["cutover_state"] in COMMITTED_STATES, "router_not_committed")
    _require(bound["router_revision"] == value["router_revision"], "anchor_revision_mismatch")
    _require(bound["legacy_generation"] == value["legacy_generation"], "anchor_legacy_generation_mismatch")
    _require(bound["legacy_issue_number"] == value["legacy_issue_number"], "anchor_legacy_issue_mismatch")
    _require(bound["final_watermark"] == value["final_watermark"], "anchor_watermark_mismatch")
    _require(bound["successor_generation"] == value["successor_generation"], "anchor_successor_generation_mismatch")
    _require(bound["successor_issue_number"] == value["successor_issue_number"], "anchor_successor_issue_mismatch")
    _require(value["cutover_anchor_sha256"] == cutover_anchor_sha256(bound), "anchor_hash_binding_mismatch")


def classify_legacy_comment(
    *,
    issue_number: int,
    comment_id: int,
    legacy_issue_number: int,
    final_watermark: Optional[int],
    frozen_comment_body_sha256: Optional[str] = None,
    observed_comment_body_sha256: Optional[str] = None,
) -> str:
    """Classify a retained legacy comment using the immutable boundary.

    source_changed is fail-closed for a selected prefix comment whose frozen
    identity/hash evidence is unavailable or contradictory.
    """

    _require(_is_int(issue_number, positive=True), "comment_issue_invalid")
    _require(_is_int(comment_id, positive=True), "comment_id_invalid")
    if issue_number != legacy_issue_number:
        return "not_legacy_segment"
    _require(final_watermark is not None and _is_int(final_watermark), "final_watermark_required")
    if comment_id > final_watermark:
        return "stale_route"
    if frozen_comment_body_sha256 is None or observed_comment_body_sha256 is None:
        return "source_changed"
    if not _is_sha256(frozen_comment_body_sha256) or not _is_sha256(observed_comment_body_sha256):
        return "source_changed"
    if frozen_comment_body_sha256 != observed_comment_body_sha256:
        return "source_changed"
    return "legacy_authority_input"


def stale_route_status(*, classification: str, comment_id: int, final_watermark: int) -> dict[str, Any]:
    """Produce the public-safe terminal status for a stale retained comment."""

    _require(classification == "stale_route", "not_stale_route")
    _require(_is_int(comment_id, positive=True) and _is_int(final_watermark), "stale_route_boundary_invalid")
    _require(comment_id > final_watermark, "stale_route_boundary_not_crossed")
    return {
        "classification": "stale_route",
        "queued": False,
        "pending": False,
        "recorded": False,
        "processor_receipt": False,
        "canonical": False,
        "retained": True,
        "auditable": True,
        "source_excluded": True,
        "disposition_required": False,
        "authority": "router_plus_immutable_cutover_anchor_plus_retired_segment_boundary",
    }


def post_protocol_decision(
    *,
    posted: bool,
    readback_verified: bool,
    router_reread_available: bool,
    before_router: Mapping[str, Any],
    after_router: Optional[Mapping[str, Any]],
    target_generation: int,
    target_issue_number: int,
) -> dict[str, Any]:
    """Classify a controller post without optimistic retry semantics."""

    before = validate_router(before_router)
    if not posted:
        return {"status": "post_failed", "retry_allowed": False, "canonical": False}
    if not readback_verified:
        return {"status": "readback_unverified", "retry_allowed": False, "canonical": False}
    if not router_reread_available or after_router is None:
        return {"status": "router_reread_unavailable", "retry_allowed": False, "canonical": False}
    after = validate_router(after_router)
    same_authority = (
        before["router_revision"] == after["router_revision"]
        and before["active_generation"] == after["active_generation"]
        and before["active_issue_number"] == after["active_issue_number"]
        and target_generation == after["active_generation"]
        and target_issue_number == after["active_issue_number"]
    )
    if same_authority:
        return {"status": "queued", "retry_allowed": False, "canonical": False}
    stale = (
        target_generation == before["active_generation"]
        and target_issue_number == before["active_issue_number"]
        and after["final_watermark"] is not None
    )
    return {
        "status": "stale_route" if stale else "authority_changed",
        "retry_allowed": bool(stale),
        "canonical": False,
        "first_post_permanently_ineligible": bool(stale),
    }


def cross_generation_identity_outcome(*, same_identity: bool, same_content: bool) -> str:
    """Return the only safe cross-generation duplicate outcome."""

    if not same_identity:
        return "new_identity"
    return "already_recorded" if same_content else "conflicting_identity"
