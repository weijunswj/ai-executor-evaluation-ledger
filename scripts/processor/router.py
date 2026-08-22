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


def _schema_validate(value: Mapping[str, Any], *, definition: str) -> None:
    schema = _load_schema()
    typed_schema = dict(schema)
    typed_schema.pop("oneOf", None)
    typed_schema["$ref"] = f"#/$defs/{definition}"
    try:
        jsonschema.Draft202012Validator.check_schema(typed_schema)
        jsonschema.Draft202012Validator(typed_schema).validate(dict(value))
    except (jsonschema.SchemaError, jsonschema.ValidationError) as error:
        raise RouterValidationError("router_schema_invalid") from error


def _validate_router_semantics(router: Mapping[str, Any]) -> dict[str, Any]:
    _schema_validate(router, definition="router")
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
    _require(router.get("record_type") == "ledger_router", "router_record_type_invalid")
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
    _require(_is_int(source_watermark), "source_watermark_invalid")
    _require(_is_sha256(source_snapshot_sha256), "source_snapshot_binding_invalid")


def validate_cutover_anchor(anchor: Mapping[str, Any]) -> dict[str, Any]:
    """Validate future immutable-anchor schema; do not create an anchor."""

    _require(isinstance(anchor, Mapping), "cutover_anchor_not_object")
    _require(anchor.get("manifest_type") == "ledger_router_cutover_anchor", "cutover_anchor_type_invalid")
    _schema_validate(anchor, definition="cutoverAnchor")
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
    if value["cutover_state"] == "CUTOVER_COMMITTED":
        _require(bound["router_revision"] == value["router_revision"], "anchor_revision_mismatch")
    else:
        _require(bound["router_revision"] < value["router_revision"], "anchor_revision_mismatch")
    _require(bound["legacy_generation"] == value["legacy_generation"], "anchor_legacy_generation_mismatch")
    _require(bound["legacy_issue_number"] == value["legacy_issue_number"], "anchor_legacy_issue_mismatch")
    _require(bound["final_watermark"] == value["final_watermark"], "anchor_watermark_mismatch")
    _require(bound["successor_generation"] == value["successor_generation"], "anchor_successor_generation_mismatch")
    _require(bound["successor_issue_number"] == value["successor_issue_number"], "anchor_successor_issue_mismatch")
    _require(value["cutover_anchor_sha256"] == cutover_anchor_sha256(bound), "anchor_hash_binding_mismatch")

def validate_legacy_drain_binding(
    router: Mapping[str, Any],
    anchor: Mapping[str, Any],
    *,
    router_revision: int,
    source_generation: int,
    source_issue_number: int,
    source_watermark: int,
    source_snapshot_sha256: str,
) -> None:
    """Bind a retired generation-0 drain to the committed immutable boundary."""

    value = validate_router(router)
    _require(value["cutover_state"] in COMMITTED_STATES, "router_not_committed")
    validate_cutover_anchor_binding(value, anchor)
    _require(router_revision == value["router_revision"], "router_revision_binding_mismatch")
    _require(source_generation == value["legacy_generation"] == 0, "legacy_generation_binding_mismatch")
    _require(source_issue_number == value["legacy_issue_number"], "legacy_issue_binding_mismatch")
    _require(source_watermark == value["final_watermark"], "legacy_watermark_binding_mismatch")
    _require(
        source_snapshot_sha256 == anchor["frozen_legacy_source_snapshot_sha256"],
        "legacy_snapshot_binding_mismatch",
    )


SEALED_SOURCE_AUTHORITY_KEYS = frozenset(
    {
        "authority_mode",
        "router_issue_number",
        "router_revision",
        "router_body_sha256",
        "cutover_state",
        "cutover_anchor_sha256",
        "router_record",
        "cutover_anchor",
        "source_generation",
        "source_issue_number",
        "source_comment_watermark",
        "source_snapshot_sha256",
    }
)


def validate_sealed_source_authority(authority: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact observed authority sealed into a v3 receipt."""

    _require(isinstance(authority, Mapping), "sealed_authority_not_object")
    _require(set(authority) == set(SEALED_SOURCE_AUTHORITY_KEYS), "sealed_authority_keys_invalid")
    _require(authority.get("authority_mode") == "router_v1", "sealed_authority_mode_invalid")
    _require(authority.get("router_issue_number") == 142, "sealed_router_issue_invalid")
    record = authority.get("router_record")
    _require(isinstance(record, Mapping), "sealed_router_record_invalid")
    router_value = validate_router(record)
    _require(authority["router_revision"] == router_value["router_revision"], "sealed_revision_mismatch")
    _require(authority["router_body_sha256"] == router_body_sha256(router_value), "sealed_router_hash_mismatch")
    _require(authority["cutover_state"] == router_value["cutover_state"], "sealed_state_mismatch")
    _require(authority["cutover_anchor_sha256"] == router_value["cutover_anchor_sha256"], "sealed_anchor_hash_mismatch")
    _require(_is_sha256(authority["router_body_sha256"]), "sealed_router_hash_invalid")
    if authority["cutover_anchor_sha256"] is not None:
        _require(_is_sha256(authority["cutover_anchor_sha256"]), "sealed_anchor_hash_invalid")
    generation = authority.get("source_generation")
    source_issue = authority.get("source_issue_number")
    watermark = authority.get("source_comment_watermark")
    snapshot = authority.get("source_snapshot_sha256")
    _require(_is_int(generation), "sealed_generation_invalid")
    _require(_is_int(source_issue, positive=True), "sealed_source_issue_invalid")
    _require(_is_int(watermark), "sealed_watermark_invalid")
    _require(_is_sha256(snapshot), "sealed_snapshot_invalid")
    anchor = authority.get("cutover_anchor")
    if generation == 0:
        _require(isinstance(anchor, Mapping), "sealed_anchor_missing")
        validate_legacy_drain_binding(
            router_value,
            anchor,
            router_revision=authority["router_revision"],
            source_generation=generation,
            source_issue_number=source_issue,
            source_watermark=watermark,
            source_snapshot_sha256=snapshot,
        )
    else:
        _require(anchor is None, "sealed_successor_anchor_unexpected")
        validate_source_segment_binding(
            router_value,
            router_revision=authority["router_revision"],
            source_generation=generation,
            source_issue_number=source_issue,
            source_watermark=watermark,
            source_snapshot_sha256=snapshot,
        )
    return dict(authority)

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
    posted_body: Optional[str] = None,
    created_comment: Optional[Mapping[str, Any]] = None,
    readback: Optional[Mapping[str, Any]] = None,
    cutover_anchor: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Classify a controller post with mechanically proven retry eligibility."""

    try:
        before = validate_router(before_router)
    except RouterValidationError:
        return {"status": "router_invalid", "retry_allowed": False, "canonical": False}
    if not posted:
        return {"status": "post_failed", "retry_allowed": False, "canonical": False}
    if not readback_verified:
        return {"status": "readback_unverified", "retry_allowed": False, "canonical": False}
    actual_readback = created_comment if created_comment is not None else readback
    if not _valid_post_readback(posted_body, actual_readback):
        return {"status": "readback_identity_unavailable", "retry_allowed": False, "canonical": False}
    if not router_reread_available or after_router is None:
        return {"status": "router_reread_unavailable", "retry_allowed": False, "canonical": False}
    try:
        after = validate_router(after_router)
        _validate_post_router_transition(before, after)
    except RouterValidationError:
        return {"status": "invalid_router_transition", "retry_allowed": False, "canonical": False}
    issue_number, comment_id = _post_readback_identity(actual_readback)
    active_target_matches_before = (
        before["cutover_state"] in ACTIVE_STATES
        and target_generation == before["active_generation"]
        and target_issue_number == before["active_issue_number"]
        and issue_number == target_issue_number
    )
    same_authority = (
        active_target_matches_before
        and after["cutover_state"] in ACTIVE_STATES
        and before["router_revision"] == after["router_revision"]
        and before["active_generation"] == after["active_generation"]
        and before["active_issue_number"] == after["active_issue_number"]
        and target_generation == after["active_generation"]
        and target_issue_number == after["active_issue_number"]
    )
    if same_authority:
        return {"status": "queued", "retry_allowed": False, "canonical": False}
    if not active_target_matches_before:
        return {"status": "ambiguous_authority", "retry_allowed": False, "canonical": False}
    # Stale retry is a legacy-only race. A successor movement must never
    # inherit retry eligibility merely because its target was once active.
    legacy_target_matches_before = (
        before["cutover_state"] == "LEGACY_ACTIVE"
        and target_generation == before["legacy_generation"]
        and target_issue_number == before["legacy_issue_number"]
        and target_generation == before["active_generation"]
        and target_issue_number == before["active_issue_number"]
        and issue_number == target_issue_number
    )
    if not legacy_target_matches_before:
        return {"status": "authority_changed", "retry_allowed": False, "canonical": False}
    if after["final_watermark"] is None or after["cutover_state"] not in COMMITTED_STATES:
        return {"status": "authority_changed", "retry_allowed": False, "canonical": False}
    if comment_id <= after["final_watermark"]:
        return {"status": "legacy_authority_input", "retry_allowed": False, "canonical": False}
    if cutover_anchor is None:
        return {"status": "stale_route_unproven", "retry_allowed": False, "canonical": False}
    try:
        validate_cutover_anchor_binding(after, cutover_anchor)
    except RouterValidationError:
        return {"status": "stale_route_unproven", "retry_allowed": False, "canonical": False}
    return {
        "status": "stale_route",
        "retry_allowed": True,
        "canonical": False,
        "first_post_permanently_ineligible": True,
    }


def _post_readback_identity(readback: Mapping[str, Any]) -> tuple[int, int]:
    issue_number = readback.get("issue_number", readback.get("issue"))
    comment_id = readback.get("id", readback.get("comment_id"))
    _require(_is_int(issue_number, positive=True), "readback_issue_invalid")
    _require(_is_int(comment_id, positive=True), "readback_comment_id_invalid")
    return issue_number, comment_id


def _valid_post_readback(posted_body: Optional[str], readback: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(posted_body, str) or not isinstance(readback, Mapping):
        return False
    try:
        _post_readback_identity(readback)
    except RouterValidationError:
        return False
    expected_hash = hashlib.sha256(posted_body.encode("utf-8")).hexdigest()
    body = readback.get("body")
    body_hash = readback.get("body_sha256")
    if body is not None and (not isinstance(body, str) or body != posted_body):
        return False
    if body_hash is not None and (not _is_sha256(body_hash) or body_hash != expected_hash):
        return False
    return body == posted_body or body_hash == expected_hash


def _validate_post_router_transition(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if before == after:
        return
    try:
        validate_router_transition(before, after)
        return
    except RouterValidationError:
        pass
    # A controller can observe the legacy state before the lock/prepared write
    # and the committed state after it. Allow only that bounded forward race.
    _require(before["cutover_state"] == "LEGACY_ACTIVE", "router_state_transition_invalid")
    _require(after["cutover_state"] in COMMITTED_STATES, "router_state_transition_invalid")
    _require(after["router_revision"] > before["router_revision"], "router_revision_not_monotonic")
    _require(after["legacy_generation"] == before["legacy_generation"], "legacy_generation_changed")
    _require(after["legacy_issue_number"] == before["legacy_issue_number"], "legacy_issue_changed")
    _require(after["rotation_threshold"] == before["rotation_threshold"], "rotation_threshold_changed")


def cross_generation_identity_outcome(*, same_identity: bool, same_content: bool) -> str:
    """Return the only safe cross-generation duplicate outcome."""

    if not same_identity:
        return "new_identity"
    return "already_recorded" if same_content else "conflicting_identity"
