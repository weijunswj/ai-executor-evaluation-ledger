"""Fail-closed, public-safe parsing for retained #142 intake comments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Set, Tuple

import jsonschema

from scripts.processor.common import (
    AUTHORIZED_PAIRS,
    FROZEN_BATCH_ID,
    FROZEN_COUNT,
    FROZEN_SNAPSHOT_SHA256,
    FROZEN_WATERMARK,
    INELIGIBLE_PAIRS,
    MODEL_ALIASES,
    PROHIBITED_IDENTITY_KEYS,
    REASONING_KEYS,
    SELF_GRADING_KEYS,
    WITHDRAWN_PAIRS,
    find_unsafe_content,
    has_forbidden_key,
    normalize_known_model,
    safe_comment_body_hash,
)

ROOT = Path(__file__).resolve().parents[2]
INTAKE_SCHEMA_PATH = ROOT / "schema" / "intake.schema.json"
INTAKE_SCHEMA = json.loads(INTAKE_SCHEMA_PATH.read_text(encoding="utf-8"))
INTAKE_VALIDATOR = jsonschema.Draft202012Validator(
    INTAKE_SCHEMA,
    format_checker=jsonschema.FormatChecker(),
)
REVIEWED_AT_VALIDATOR = jsonschema.Draft202012Validator(
    INTAKE_SCHEMA["properties"]["reviewed_at"],
    format_checker=jsonschema.FormatChecker(),
)

INTAKE_MARKER = "<!-- ledger-intake:v1 -->"
WITHDRAWN_COMMENT_IDS = frozenset({5088187239})

SCORE_FIELDS = (
    "correctness",
    "safety_and_scope_control",
    "evidence_quality",
    "operational_judgement",
    "task_understanding",
    "tracker_and_repository_hygiene",
    "autonomy",
    "efficiency",
)

EVIDENCE_FIELDS = (
    "first_pass_accepted",
    "controller_intervention_required",
    "safe_final_state_reported",
    "safe_final_state_verified",
    "root_cause_identified",
    "root_cause_result",
    "follow_up_count",
    "confidence",
    "verified_strengths",
    "verified_defects",
    "integrity_and_control_flags",
)

RAW_ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "record_type",
        "controller_run_id",
        "evaluation_run_id",
        "run_id",
        "provider",
        "canonical_base_model",
        "model",
        "base_model",
        "evaluation_protocol",
        "protocol",
        "repository_alias",
        "subject_alias",
        "issue_number",
        "pull_request_number",
        "source_revision",
        "source_binding",
        "revision_binding",
        "task_class",
        "difficulty",
        "verdict",
        "outcome",
        "gate_disposition",
        "score_dimensions",
        "score",
        "weighted_score_5",
        "weighted_score_10",
        "public_safe_evidence",
        "evidence",
        "secret_exposure_status",
        "secret_exposure",
        "secret_exposure_audit",
        "reviewed_at",
        "executor_reported_at",
        "prompt_sha256",
        "objective",
    }
)

LEGACY_ALIAS_PAIRS = (
    ("evaluation_run_id", "run_id"),
    ("canonical_base_model", "model"),
    ("canonical_base_model", "base_model"),
    ("evaluation_protocol", "protocol"),
    ("repository_alias", "subject_alias"),
    ("source_revision", "source_binding"),
    ("source_revision", "revision_binding"),
    ("verdict", "outcome"),
    ("verdict", "gate_disposition"),
    ("score_dimensions", "score"),
    ("public_safe_evidence", "evidence"),
    ("secret_exposure_status", "secret_exposure"),
    ("secret_exposure_status", "secret_exposure_audit"),
)

VERDICT_VALUES = frozenset(
    {
        "accepted",
        "pass",
        "amend",
        "hold",
        "fail",
        "blocked",
        "rejected",
        "rescheduled",
        "error",
        "reset",
        "owner_withdrawn",
        "withdrawn",
    }
)


@dataclass(frozen=True)
class HistoricalReviewTimestampAuthority:
    """Closed, fingerprint-bound authority for the one frozen migration."""

    batch_id: str
    comment_id: int
    frozen_comment_ids: FrozenSet[int]
    verified_snapshot_sha256: str
    source_body_sha256: str
    expected_body_sha256: str
    source_created_at: Any
    expected_created_at: Any
    source_updated_at: Any
    expected_updated_at: Any

    def reviewed_at_for(self, body: str) -> Optional[str]:
        if (
            self.batch_id != FROZEN_BATCH_ID
            or len(self.frozen_comment_ids) != FROZEN_COUNT
            or self.comment_id not in self.frozen_comment_ids
            or max(self.frozen_comment_ids, default=0) != FROZEN_WATERMARK
            or self.verified_snapshot_sha256 != FROZEN_SNAPSHOT_SHA256
            or self.source_body_sha256 != self.expected_body_sha256
            or self.source_body_sha256 != safe_comment_body_hash(body)
            or self.source_created_at != self.expected_created_at
            or self.source_updated_at != self.expected_updated_at
            or not isinstance(self.source_created_at, str)
            or any(REVIEWED_AT_VALIDATOR.iter_errors(self.source_created_at))
        ):
            return None
        return self.source_created_at


def _reject(code: str) -> Tuple[str, Dict[str, Any], str]:
    """Return a disposition without retaining or echoing source values."""

    return code, {}, code


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _same_or_missing(left: Any, right: Any) -> bool:
    return left is None or right is None or left == right


def _copy_alias(adapted: Dict[str, Any], target: str, source: str) -> bool:
    if target in adapted and source in adapted and adapted[target] != adapted[source]:
        return False
    if target not in adapted and source in adapted:
        adapted[target] = adapted[source]
    return True


def _adapt_evidence(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    result = dict(value)
    if "follow_up_count" in result and "follow_up_runs_required" in result:
        if result["follow_up_count"] != result["follow_up_runs_required"]:
            return None
    if "follow_up_count" not in result and "follow_up_runs_required" in result:
        result["follow_up_count"] = result["follow_up_runs_required"]
    result.pop("follow_up_runs_required", None)
    return result


def adapt_historical_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply only the exact aliases authorised by the historical contract."""

    if not isinstance(payload, dict):
        return {}
    if any(key not in RAW_ALLOWED_KEYS for key in payload):
        return {}

    adapted = dict(payload)
    for target, source in LEGACY_ALIAS_PAIRS:
        if not _copy_alias(adapted, target, source):
            return {}

    if "canonical_base_model" in adapted:
        adapted["canonical_base_model"] = normalize_known_model(adapted["canonical_base_model"])
    if "verdict" in adapted and isinstance(adapted["verdict"], str):
        lowered = adapted["verdict"].lower()
        if lowered in VERDICT_VALUES:
            adapted["verdict"] = lowered

    if "public_safe_evidence" in adapted:
        evidence = _adapt_evidence(adapted["public_safe_evidence"])
        if evidence is None:
            return {}
        adapted["public_safe_evidence"] = evidence

    for _, source in LEGACY_ALIAS_PAIRS:
        adapted.pop(source, None)
    return adapted


def _schema_valid(payload: Dict[str, Any]) -> bool:
    return not any(INTAKE_VALIDATOR.iter_errors(payload))


REQUIRED_AUTHORITY_FIELDS = (
        "schema_version",
        "record_type",
        "controller_run_id",
        "evaluation_run_id",
        "provider",
        "canonical_base_model",
        "evaluation_protocol",
        "repository_alias",
        "source_revision",
        "task_class",
        "difficulty",
        "verdict",
        "score_dimensions",
        "weighted_score_5",
        "public_safe_evidence",
        "secret_exposure_status",
        "reviewed_at",
)


def _required_authority_present(payload: Dict[str, Any]) -> bool:
    return all(key in payload for key in REQUIRED_AUTHORITY_FIELDS)


def _otherwise_valid_for_historical_reviewed_at(
    payload: Dict[str, Any],
    reviewed_at: str,
) -> bool:
    if any(
        key not in payload
        for key in REQUIRED_AUTHORITY_FIELDS
        if key != "reviewed_at"
    ):
        return False
    candidate = dict(payload)
    candidate["reviewed_at"] = reviewed_at
    return not any(INTAKE_VALIDATOR.iter_errors(candidate))


def contains_reasoning_keys(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in REASONING_KEYS or contains_reasoning_keys(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_reasoning_keys(child) for child in value)
    return False


def contains_prohibited_identity_or_secrets(value: Any) -> Tuple[bool, bool]:
    """Return only booleans so rejected source values cannot enter diagnostics."""

    if isinstance(value, dict):
        for key, child in value.items():
            if key in PROHIBITED_IDENTITY_KEYS:
                return True, False
            found, secret = contains_prohibited_identity_or_secrets(child)
            if found:
                return True, secret
    elif isinstance(value, list):
        for child in value:
            found, secret = contains_prohibited_identity_or_secrets(child)
            if found:
                return True, secret
    elif isinstance(value, str):
        if find_unsafe_content(value):
            return True, True
    return False, False


def parse_intake_comment(
    comment_id: int,
    body: str,
    recorded_run_ids: Set[str],
    seen_candidate_ids: Set[str],
    *,
    historical_review_authority: Optional[
        HistoricalReviewTimestampAuthority
    ] = None,
) -> Tuple[str, Dict[str, Any], str]:
    """Parse exactly one tainted comment into an admitted payload or safe code."""

    if comment_id in WITHDRAWN_COMMENT_IDS:
        return _reject("withdrawn_identity")
    if not isinstance(body, str) or not body.startswith(INTAKE_MARKER):
        return _reject("no_marker")
    if find_unsafe_content(body):
        return _reject("unsafe_content")

    raw = body[len(INTAKE_MARKER) :].lstrip(" \t\r\n")
    if not raw:
        return _reject("invalid_schema")
    try:
        payload, end = json.JSONDecoder(parse_constant=_reject_nonfinite_constant).raw_decode(raw)
    except (TypeError, ValueError):
        return _reject("invalid_schema")
    if not isinstance(payload, dict) or raw[end:].strip():
        return _reject("invalid_schema")
    if contains_reasoning_keys(payload) or has_forbidden_key(payload):
        return _reject("ineligible_identity")
    identity_found, identity_is_secret = contains_prohibited_identity_or_secrets(payload)
    if identity_found:
        return _reject("unsafe_content" if identity_is_secret else "ineligible_identity")

    adapted = adapt_historical_payload(payload)
    if not adapted:
        return _reject("invalid_schema")
    if "reviewed_at" not in adapted and historical_review_authority is not None:
        reviewed_at = historical_review_authority.reviewed_at_for(body)
        if (
            reviewed_at is not None
            and _otherwise_valid_for_historical_reviewed_at(
                adapted,
                reviewed_at,
            )
        ):
            adapted["reviewed_at"] = reviewed_at
    if not _required_authority_present(adapted):
        return _reject("authority_missing")

    schema_errors = tuple(INTAKE_VALIDATOR.iter_errors(adapted))
    provider = adapted["provider"]
    model = adapted["canonical_base_model"]
    pair = (provider, model)
    if pair in WITHDRAWN_PAIRS:
        return _reject("withdrawn_identity")
    if pair in INELIGIBLE_PAIRS:
        return _reject("ineligible_identity")
    if pair not in AUTHORIZED_PAIRS:
        return _reject("unsupported_identity")
    if schema_errors:
        return _reject("invalid_schema")
    if adapted["verdict"] == "blocked":
        return _reject("ineligible_identity")
    if adapted["secret_exposure_status"] != "none":
        return _reject("unsafe_content")

    run_id = adapted["evaluation_run_id"]
    if run_id in recorded_run_ids:
        return _reject("already_recorded")
    if run_id in seen_candidate_ids:
        return _reject("duplicate_identity")
    seen_candidate_ids.add(run_id)
    return "admitted", adapted, "admitted"


def canonical_record_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Construct a canonical record field-by-field from validated authority."""

    evidence = payload["public_safe_evidence"]
    record: Dict[str, Any] = {
        "schema_version": 2,
        "record_type": "evaluation",
        "run_id": payload["evaluation_run_id"],
        "reviewed_at": payload["reviewed_at"],
        "provider": payload["provider"],
        "model": payload["canonical_base_model"],
        "evaluation_protocol": payload["evaluation_protocol"],
        "task_class": payload["task_class"],
        "difficulty": payload["difficulty"],
        "subject_alias": payload["repository_alias"],
        "revision_binding": payload["source_revision"],
        "outcome": payload["verdict"],
        "first_pass_accepted": evidence["first_pass_accepted"],
        "controller_intervention_required": evidence["controller_intervention_required"],
        "scores": {field: payload["score_dimensions"][field] for field in SCORE_FIELDS},
        "weighted_score_5": payload["weighted_score_5"],
        "confidence": evidence["confidence"],
    }

    optional_top_level = (
        "executor_reported_at",
        "prompt_sha256",
        "weighted_score_10",
        "objective",
    )
    for field in optional_top_level:
        if field in payload:
            record[field] = payload[field]

    for field in EVIDENCE_FIELDS:
        if field in evidence and field not in record:
            record[field] = evidence[field]
    return record
