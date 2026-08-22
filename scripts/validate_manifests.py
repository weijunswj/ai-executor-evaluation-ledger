#!/usr/bin/env python3
"""Fail-closed validation for the historical ledger migration manifests."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_BASE_SHA = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
SOURCE_CANDIDATE_SHA = "45990433a0f8199f056d1ad71a51f934b3bae7aa"
CORRECTION_ORDER_AUTHORITY_SHA = "223e6ecc24c84421a4bab60fcf87472b1d620744"
TARGET_EVALUATIONS_SHA = "387dfc1347189555ef91eabf767e62738f777b2e80b79f5378e95170df40cb64"
TARGET_DISPOSITIONS_SHA = "17a95e2e35889115afc6b1130aa2c836d6bff12815126a6547263e8e85b2ff7d"
TARGET_OUTPUT_HASHES = {
    "README.md": "c2564c634a1709dcbc7712473c420ac679aa654e242a8dc1ccf693768fa8e8ba",
    "scorecard.md": "7db9da098abdd88335fbcf8b7ca8193f8e0476f0a8530687878d49b6529cbcbb",
    "analysis/model-recommendation.json": "8408f47f19176fd14b38beeab8d1e524137bf5e2aeecb545b016d0da4fba63a8",
    "ledger/dispositions.jsonl": TARGET_DISPOSITIONS_SHA,
}

MANIFEST_PATHS = {
    "base-model-v2.json": "base_model_v2_migration",
    "correction-migration-manifest.json": "correction_migration_manifest",
    "evaluation-protocol-v1.json": "evaluation_protocol_v1",
    "historical-intake-adapter-manifest.json": "historical_intake_adapter_manifest",
    "historical-direct-controller-bypass-reconciliation.json": "historical_direct_controller_bypass_reconciliation",
    "preservation-manifest.json": "canonical_base_preservation_manifest",
    "reasoning-scrub-receipt.json": "reasoning_scrub_receipt",
    "unicode-identity-history-activation.json": "unicode_identity_history_activation",
}
HISTORICAL_MANIFEST_PATHS = {
    name: manifest_type
    for name, manifest_type in MANIFEST_PATHS.items()
    if name != "historical-direct-controller-bypass-reconciliation.json"
}
G3_MANIFESTS = {
    "base-model-v2.json",
    "correction-migration-manifest.json",
    "historical-direct-controller-bypass-reconciliation.json",
    "reasoning-scrub-receipt.json",
}
LEGACY_MANIFESTS = set(MANIFEST_PATHS) - G3_MANIFESTS

OPAQUE_SUBJECT_PATTERN = r"^subject-[0-9a-f]{64}$"
OPAQUE_SELECTOR_PATTERN = r"^selector-sha256-[0-9a-f]{64}$"
REASONING_REMOVED_RECORD_SHA = "5b7e12fcb75b9a9d1b05655857ec47e44f7d856c5bed7bed45abc52012758176"
CANDIDATE_ALLOWED_FILES = [
    "README.md",
    "evaluations.jsonl",
    "migrations/base-model-v2.json",
    "migrations/correction-migration-manifest.json",
    "migrations/correction-records-v3.jsonl",
    "migrations/reasoning-scrub-receipt.json",
    "schema/correction-v3.schema.json",
    "schema/disposition.schema.json",
    "schema/manifest.schema.json",
    "schema/receipt.schema.json",
    "scorecard.md",
    "scripts/processor/frozen_replay.py",
    "scripts/rebuild_views.py",
    "scripts/validate_manifests.py",
    "scripts/validate_receipts.py",
    "tests/test_check_public_safety.py",
    "tests/test_frozen_replay.py",
    "tests/test_manifest_validation.py",
    "tests/test_migration.py",
    "tests/test_receipt_validation.py",
]
HISTORICAL_BYPASS_ENTRIES = (
    {
        "evaluation_run_id": "2026-08-11-ledger-pr156-already-recorded-binding-amendment-082",
        "canonical_record_sha256": "a0bdf428c012bae1d7db1803050413e3c8b24b44759bd5d5b49945150a263a2f",
        "canonical_entry_commit_sha": "58fdb089df2e85f9d3358d7ed68bd4e963e29ebc",
        "pull_request_number": 168,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
    {
        "evaluation_run_id": "2026-08-12-ledger-pr156-f1-prefix-final-g3-105",
        "canonical_record_sha256": "cd67b187a8b879a4059e951cf30c0ed7253ff5fc02cb13fca9cf02dc2cec1178",
        "canonical_entry_commit_sha": "e088fb2ff1bc71be328b0d23c3e2564a4cbaa29e",
        "pull_request_number": 169,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
    {
        "evaluation_run_id": "2026-08-13-ledger-pr156-f1-two-test-debt-final-g3-106",
        "canonical_record_sha256": "58c73454fae177cf685e2fcb0965102ede0282e53340f5f2765c36da7ddf55d5",
        "canonical_entry_commit_sha": "d49c9029e3bc68365ce7fc2ead17faae5c094ab3",
        "pull_request_number": 172,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
    {
        "evaluation_run_id": "2026-08-13-ledger-pr156-f1-expanded-test-debt-final-g3-107",
        "canonical_record_sha256": "a7762721a45ae65fbf800f31d94ab1b42758dda5ab2bf44b615a39d5df40b07f",
        "canonical_entry_commit_sha": "464e98dfb08e729c15662834d91d4f1e0e43e2ad",
        "pull_request_number": 173,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
    {
        "evaluation_run_id": "2026-08-13-ledger-pr156-f1-receipt-contract-final-g3-108",
        "canonical_record_sha256": "5a320e42016677bcd4183e492b9e47611a3288c52ce3f4c6e6a88f86d9a78837",
        "canonical_entry_commit_sha": "f01bab84d08ac3cfc6d138a96a2dcaebd6109ccb",
        "pull_request_number": 175,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
    {
        "evaluation_run_id": "2026-08-13-ledger-pr156-f1-receipt-contract-public-safety-final-g3-109",
        "canonical_record_sha256": "44ee850bd79d4301ade550a4ebdd307cd4371f9fc67332fc87263357e56886c8",
        "canonical_entry_commit_sha": "38891edbfc7bce7bcade8cbd1f399af17da218a1",
        "pull_request_number": 176,
        "route": "legacy_direct_controller_evaluation",
        "source_comment_status": "absent_at_reconciliation_snapshot",
        "processor_receipt_status": "absent_not_applicable",
        "reconciliation_status": "canonical_existing_legacy_direct_route",
    },
)
HISTORICAL_BYPASS_RUN_IDS = frozenset(entry["evaluation_run_id"] for entry in HISTORICAL_BYPASS_ENTRIES)
HISTORICAL_BYPASS_MANIFEST_PATH = "historical-direct-controller-bypass-reconciliation.json"
HISTORICAL_BYPASS_RECONCILED_AT = "2026-08-22T06:52:02Z"
HISTORICAL_BYPASS_SOURCE_SNAPSHOT = {
    "issue_number": 142,
    "comment_count": 874,
    "min_comment_id": 5084152024,
    "max_comment_id": 5374312204,
    "watermark": 5374312204,
    "snapshot_sha256": "b9252b5f38ad527410943bb35bb6d5baecb961af2e14f0f8e174eb0c6f011478",
    "matching_expected_run_ids": [],
}
HISTORICAL_BYPASS_RECEIPT_SNAPSHOT = {
    "issue_number": 143,
    "comment_count": 1,
    "min_comment_id": 5372948110,
    "max_comment_id": 5372948110,
    "watermark": 5372948110,
    "snapshot_sha256": "f761cea53baf10b95f20cb68293975a945163a0409939d681e09f0c9881afd99",
    "matching_expected_run_ids": [],
}


def _historical_bypass_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "historical_direct_controller_bypass_reconciliation",
        "authority_scope": "historical_reconciliation_only_no_admission_no_receipt_no_cleanup_no_rewrite",
        "reconciled_at": HISTORICAL_BYPASS_RECONCILED_AT,
        "canonical_base_sha": "d38852a98b630bf1bd39ce62bf8e5d1e2921f39d",
        "expected_entry_count": 6,
        "record_hash_spec": {
            "algorithm": "SHA-256",
            "byte_representation": "exact_stored_UTF-8_evaluations.jsonl_line_including_terminal_LF",
            "json_reserialization": False,
        },
        "source_snapshot": dict(HISTORICAL_BYPASS_SOURCE_SNAPSHOT),
        "receipt_snapshot": dict(HISTORICAL_BYPASS_RECEIPT_SNAPSHOT),
        "entries": [dict(entry) for entry in HISTORICAL_BYPASS_ENTRIES],
    }



class ManifestValidationError(RuntimeError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _closed_set_hash(values: list[str]) -> str:
    return _sha256((json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":")) + "\n").encode())


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite_json_number:{value}")


def _duplicate_rejecting_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestValidationError("duplicate_json_key")
        result[key] = value
    return result


def _parse_json(raw: bytes) -> Any:
    if not raw or raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ManifestValidationError("json_bytes_invalid")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_rejecting_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ManifestValidationError("json_invalid")


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _canonical_record_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _evaluation_line_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _git_object(root: Path, revision: str, relative_path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{revision}:{relative_path}"], cwd=root, capture_output=True, check=False)
    if result.returncode != 0:
        raise ManifestValidationError("manifest_authority_unavailable")
    return result.stdout


def _records(raw: bytes) -> list[dict[str, Any]]:
    if b"\r" in raw or raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise ManifestValidationError("manifest_records_bytes_invalid")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        if not line.endswith(b"\n") or line.endswith(b"\r\n"):
            raise ManifestValidationError("manifest_record_delimiter_invalid")
        try:
            value = json.loads(line.decode("utf-8", errors="strict"), object_pairs_hook=_duplicate_rejecting_pairs, parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ManifestValidationError("manifest_records_invalid")
        if not isinstance(value, dict) or not isinstance(value.get("run_id"), str) or value["run_id"] in seen:
            raise ManifestValidationError("manifest_records_invalid")
        seen.add(value["run_id"])
        records.append(value)
    return records


def _load_correction_records(root: Path) -> tuple[bytes, list[dict[str, Any]]]:
    path = root / "migrations" / "correction-records-v3.jsonl"
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestValidationError("correction_records_unavailable") from error
    if b"\r" in raw or raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ManifestValidationError("correction_records_bytes_invalid")
    values: list[dict[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise ManifestValidationError("correction_record_delimiter_invalid")
        try:
            value = json.loads(line.decode("utf-8", errors="strict"), object_pairs_hook=_duplicate_rejecting_pairs, parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ManifestValidationError("correction_records_invalid")
        if not isinstance(value, dict):
            raise ManifestValidationError("correction_records_invalid")
        values.append(value)
    return raw, values


def _locked_correction_order(root: Path) -> list[tuple[Any, Any, Any, Any]]:
    raw = _git_object(
        root,
        CORRECTION_ORDER_AUTHORITY_SHA,
        "migrations/correction-records-v3.jsonl",
    )
    if b"\r" in raw or raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise ManifestValidationError("correction_order_authority_invalid")
    order: list[tuple[Any, Any, Any, Any]] = []
    for line in raw.splitlines(keepends=True):
        try:
            value = json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_duplicate_rejecting_pairs,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ManifestValidationError("correction_order_authority_invalid")
        if not isinstance(value, dict):
            raise ManifestValidationError("correction_order_authority_invalid")
        order.append(
            (
                value.get("correction_id"),
                value.get("target", {}).get("run_id") if isinstance(value.get("target"), dict) else None,
                value.get("record_type"),
                value.get("lineage", {}).get("sequence") if isinstance(value.get("lineage"), dict) else None,
            )
        )
    return order



def _effective_record(record: Mapping[str, Any], score_values: Optional[tuple[str, str]]) -> dict[str, Any]:
    value = copy.deepcopy(dict(record))
    if score_values is not None:
        try:
            numeric_scores = tuple(float(score) for score in score_values)
        except (TypeError, ValueError) as error:
            raise ManifestValidationError("score_binding_invalid") from error
        if len(numeric_scores) != 2 or any(not math.isfinite(score) for score in numeric_scores):
            raise ManifestValidationError("score_binding_invalid")
        value["weighted_score_5"], value["weighted_score_10"] = numeric_scores
    return value


def _proof(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _canonical_record_bytes(value)
    return {
        "encoding": "UTF-8",
        "newline": "LF",
        "canonicalization": "sorted-key JSON, compact separators, terminal LF",
        "sha256": _sha256(raw),
        "byte_length": len(raw),
        "unsafe_bytes_repeated": False,
    }


def _source_record_sha256(record: Mapping[str, Any]) -> str:
    return _sha256(json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _source_binding_sha256(record: Mapping[str, Any]) -> str:
    return _sha256(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _source_rows(root: Path, revision: str) -> list[dict[str, Any]]:
    return _records(_git_object(root, revision, "evaluations.jsonl"))


def _public_bindings(root: Path = ROOT, rows: Optional[list[dict[str, Any]]] = None) -> tuple[list[str], list[str], dict[str, tuple[str, str]], dict[str, str], str]:
    if rows is None:
        _, rows = _load_correction_records(root)
    withdrawn = [row["target"]["run_id"] for row in rows if row["record_type"] == "withdrawal"]
    redactions = [row["target"]["run_id"] for row in rows if row["record_type"] == "public_safe_redaction"]
    scores: dict[str, tuple[str, str]] = {}
    replacements: dict[str, str] = {}
    for row in rows:
        if row["record_type"] == "factual_correction":
            changes = row["correction"].get("field_changes", [])
            ordered = [str(change["after_public_safe"]) for change in changes]
            if len(ordered) != 2:
                raise ManifestValidationError("score_binding_invalid")
            scores[row["target"]["run_id"]] = (ordered[0], ordered[1])
        if row["record_type"] == "base_model_replacement":
            replacements[row["replacement"]["removed_run_id"]] = row["replacement"]["replacement_run_id"]
    return withdrawn, redactions, scores, replacements, f"subject-{REASONING_REMOVED_RECORD_SHA}"


def source_bound_public_bindings(
    root: Path = ROOT,
    rows: Optional[list[dict[str, Any]]] = None,
) -> tuple[set[str], dict[str, str], dict[str, tuple[str, str]], str]:
    """Return opaque bindings keyed by immutable source-record SHA-256.

    Replay resolves these bindings against the supplied canonical-main bytes.
    The returned keys never contain source identity values or public run IDs.
    """

    if rows is None:
        _, rows = _load_correction_records(root)
    withdrawn_source_shas = {
        row["target"]["original_record_sha256"]
        for row in rows
        if row["record_type"] == "withdrawal"
    }
    replacement_source_shas = {
        row["target"]["original_record_sha256"]: row["replacement"]["replacement_run_id"]
        for row in rows
        if row["record_type"] == "base_model_replacement"
    }
    score_source_shas = {
        row["target"]["original_record_sha256"]: tuple(
            str(change["after_public_safe"])
            for change in row["correction"].get("field_changes", [])
        )
        for row in rows
        if row["record_type"] == "factual_correction"
    }
    return (
        withdrawn_source_shas,
        replacement_source_shas,
        score_source_shas,
        REASONING_REMOVED_RECORD_SHA,
    )


def _source_subject_index(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_subject: dict[str, dict[str, Any]] = {}
    by_source_id: dict[str, dict[str, Any]] = {}
    for revision in (SOURCE_BASE_SHA, SOURCE_CANDIDATE_SHA):
        for row in _source_rows(root, revision):
            subject = f"subject-{_source_record_sha256(row)}"
            by_subject.setdefault(subject, row)
            by_source_id.setdefault(row["run_id"], row)
    return by_subject, by_source_id


def _proof_is_closed(value: Mapping[str, Any]) -> bool:
    return (
        set(value) == {"encoding", "newline", "canonicalization", "sha256", "byte_length", "unsafe_bytes_repeated"}
        and value.get("encoding") == "UTF-8"
        and value.get("newline") == "LF"
        and value.get("canonicalization") == "sorted-key JSON, compact separators, terminal LF"
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None
        and isinstance(value.get("byte_length"), int)
        and value["byte_length"] > 0
        and value.get("unsafe_bytes_repeated") is False
    )


def _correction_proof_bindings(
    records: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    main_rows: list[dict[str, Any]],
    final_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any], bool]]:
    candidate_by_subject = {
        f"subject-{_source_record_sha256(row)}": row for row in candidate_rows
    }
    base_by_run = {row["run_id"]: row for row in main_rows}
    final_by_run = {row["run_id"]: row for row in final_rows}
    source_by_binding = {
        _source_binding_sha256(row): row for row in main_rows
    }
    if len(source_by_binding) != len(main_rows):
        raise ManifestValidationError("source_membership_ambiguous")

    bindings: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
    for record in records:
        kind = record["record_type"]
        target = record["target"]
        try:
            if kind in {"authority_gap", "factual_correction"}:
                source = candidate_by_subject[target["run_id"]]
                after_source = final_by_run[source["run_id"]]
                after_is_final = True
            elif kind == "public_safe_redaction":
                candidate_source = candidate_by_subject[target["run_id"]]
                source = base_by_run[candidate_source["run_id"]]
                after_source = final_by_run[source["run_id"]]
                after_is_final = True
            elif kind == "withdrawal":
                source = source_by_binding[target["original_record_sha256"]]
                if source["run_id"] in final_by_run:
                    raise ManifestValidationError("withdrawal_source_present")
                after_source = source
                after_is_final = False
            elif kind == "base_model_replacement":
                source = source_by_binding[target["original_record_sha256"]]
                if source["run_id"] in final_by_run:
                    raise ManifestValidationError("replacement_source_present")
                replacement_subject = record["replacement"]["replacement_run_id"]
                replacement_candidate = candidate_by_subject[replacement_subject]
                after_source = final_by_run[replacement_candidate["run_id"]]
                after_is_final = True
            else:
                raise ManifestValidationError("correction_record_type_invalid")
        except KeyError as error:
            raise ManifestValidationError("correction_source_membership_missing") from error
        bindings.append((_proof(source), _proof(after_source), after_is_final))
    return bindings



def validate_correction_records(
    root: Path = ROOT,
    *,
    final_raw: Optional[bytes] = None,
) -> dict[str, Any]:
    raw, records = _load_correction_records(root)
    schema = _parse_json((root / "schema" / "correction-v3.schema.json").read_bytes())
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for record in records:
            validator.validate(record)
    except (OSError, UnicodeDecodeError, ValueError, jsonschema.SchemaError, jsonschema.ValidationError) as error:
        raise ManifestValidationError("correction_schema_failure") from error
    if len(records) != 116 or len({record["correction_id"] for record in records}) != len(records):
        raise ManifestValidationError("correction_record_count_or_id_mismatch")
    current_order = [
        (
            record["correction_id"],
            record["target"]["run_id"],
            record["record_type"],
            record["lineage"]["sequence"],
        )
        for record in records
    ]
    if current_order != _locked_correction_order(root):
        raise ManifestValidationError("correction_ordering_mismatch")

    by_subject, _ = _source_subject_index(root)
    candidate_rows = _source_rows(root, SOURCE_CANDIDATE_SHA)
    main_rows = _source_rows(root, SOURCE_BASE_SHA)
    if final_raw is None:
        final_raw = (root / "evaluations.jsonl").read_bytes()
    final_rows = _records(final_raw)
    candidate_subject_by_id = {row["run_id"]: f"subject-{_source_record_sha256(row)}" for row in candidate_rows}
    final_ids = {row["run_id"] for row in final_rows}
    if set(candidate_subject_by_id) != final_ids or len(final_ids) != 59:
        raise ManifestValidationError("candidate_record_set_mismatch")
    score_source_shas = source_bound_public_bindings(root, records)[2]
    expected_final_rows = [
        _effective_record(row, score_source_shas.get(_source_record_sha256(row)))
        for row in candidate_rows
    ]
    expected_final_raw = b"".join(_evaluation_line_bytes(row) for row in expected_final_rows)
    if final_raw != expected_final_raw:
        raise ManifestValidationError("effective_final_record_mismatch")
    proof_bindings = _correction_proof_bindings(
        records,
        candidate_rows,
        main_rows,
        final_rows,
    )
    withdrawn, redactions, scores, replacements, removed_subject = _public_bindings(root, records)
    final_subjects = {candidate_subject_by_id[row["run_id"]] for row in final_rows}
    main_subjects = {
        candidate_subject_by_id[row["run_id"]]
        for row in main_rows
        if row["run_id"] in candidate_subject_by_id
    } | set(withdrawn)
    for index, record in enumerate(records):
        target = record["target"]
        if target["run_id"] != f"subject-{target['original_record_sha256']}":
            raise ManifestValidationError("opaque_subject_binding_mismatch")
        if f"subject-{target['original_record_sha256']}" not in by_subject:
            if record["record_type"] not in {"withdrawal", "base_model_replacement"}:
                raise ManifestValidationError("source_record_binding_missing")
        if record["original_identity"]["identity_sha256"] != target["original_record_sha256"]:
            raise ManifestValidationError("identity_binding_mismatch")
        if not _proof_is_closed(record["before"]) or not _proof_is_closed(record["after"]):
            raise ManifestValidationError("proof_binding_invalid")
        expected_before, expected_after, _ = proof_bindings[index]
        if record["before"] != expected_before:
            raise ManifestValidationError("correction_before_proof_mismatch")
        if record["after"] != expected_after:
            raise ManifestValidationError("correction_after_proof_mismatch")
        if record["record_type"] == "public_safe_redaction":
            for change in record["correction"].get("field_changes", []):
                if re.fullmatch(OPAQUE_SELECTOR_PATTERN, change["path"]) is None:
                    raise ManifestValidationError("selector_binding_invalid")

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for index, record in enumerate(records):
        by_kind.setdefault(record["record_type"], []).append(record)
    if len(by_kind.get("authority_gap", [])) != 59 or len(by_kind.get("public_safe_redaction", [])) != 25 or len(by_kind.get("factual_correction", [])) != 19 or len(by_kind.get("withdrawal", [])) != 10 or len(by_kind.get("base_model_replacement", [])) != 3:
        raise ManifestValidationError("correction_lineage_counts_mismatch")
    if {record["target"]["run_id"] for record in by_kind["authority_gap"]} != final_subjects:
        raise ManifestValidationError("authority_gap_target_set_mismatch")
    if set(withdrawn) != main_subjects - final_subjects:
        raise ManifestValidationError("withdrawal_target_set_mismatch")
    if set(redactions) & set(withdrawn):
        raise ManifestValidationError("redaction_withdrawal_overlap")
    if set(scores) & set(withdrawn):
        raise ManifestValidationError("score_withdrawal_overlap")
    if set(replacements) != {record["replacement"]["removed_run_id"] for record in by_kind["base_model_replacement"]}:
        raise ManifestValidationError("replacement_target_set_mismatch")
    seen_ids: dict[str, int] = {}
    previous_by_chain: dict[tuple[str, str], Optional[str]] = {}
    for index, record in enumerate(records):
        target = record["target"]
        rid = target["run_id"]
        kind = record["record_type"]
        seen_ids[rid] = seen_ids.get(rid, 0) + 1
        if record["correction_id"] != f"corr-v3-{rid}-{seen_ids[rid]:04d}":
            raise ManifestValidationError("correction_id_sequence_mismatch")
        chain = (rid, kind)
        expected_type_sequence = sum(1 for prior in records[:index] if (prior["target"]["run_id"], prior["record_type"]) == chain) + 1
        if record["lineage"]["sequence"] != expected_type_sequence or record["lineage"]["prior_correction_sha256"] != previous_by_chain.get(chain):
            raise ManifestValidationError("correction_lineage_chain_mismatch")
        probe = copy.deepcopy(record)
        probe["lineage"]["correction_sha256"] = None
        if record["lineage"]["correction_sha256"] != _sha256(_canonical_record_bytes(probe)):
            raise ManifestValidationError("correction_lineage_hash_mismatch")
        previous_by_chain[chain] = record["lineage"]["correction_sha256"]
        if kind == "factual_correction":
            if rid not in scores or tuple(str(change["after_public_safe"]) for change in record["correction"]["field_changes"]) != scores[rid]:
                raise ManifestValidationError("score_binding_mismatch")
        if kind == "withdrawal" and record["withdrawal"]["withdrawn_run_id"] != rid:
            raise ManifestValidationError("withdrawal_binding_mismatch")
        if kind == "base_model_replacement":
            if replacements.get(record["replacement"]["removed_run_id"]) != record["replacement"]["replacement_run_id"]:
                raise ManifestValidationError("replacement_binding_mismatch")
    if len(seen_ids) != 69 or removed_subject not in set(withdrawn):
        raise ManifestValidationError("correction_target_accounting_mismatch")
    return {
        "record_count": len(records),
        "sha256": _sha256(raw),
        "counts": {key: len(value) for key, value in by_kind.items()},
        "proofs_checked": len(proof_bindings),
        "before_proofs_recomputed": len(proof_bindings),
        "after_proofs_recomputed": sum(1 for _, _, is_final in proof_bindings if is_final),
        "withdrawal_absence_checks": sum(1 for _, _, is_final in proof_bindings if not is_final),
    }


def rewrite_correction_proofs(root: Path = ROOT) -> dict[str, int]:
    """Regenerate correction proofs and all dependent lineage hashes."""

    _, records = _load_correction_records(root)
    candidate_rows = _source_rows(root, SOURCE_CANDIDATE_SHA)
    main_rows = _source_rows(root, SOURCE_BASE_SHA)
    final_rows = _records((root / "evaluations.jsonl").read_bytes())
    proof_bindings = _correction_proof_bindings(
        records,
        candidate_rows,
        main_rows,
        final_rows,
    )
    updated: list[dict[str, Any]] = []
    previous_by_chain: dict[tuple[str, str], Optional[str]] = {}
    changed_after = 0
    for record, (before, after, _) in zip(records, proof_bindings):
        if record["after"] != after:
            changed_after += 1
        value = copy.deepcopy(record)
        value["before"] = before
        value["after"] = after
        chain = (value["target"]["run_id"], value["record_type"])
        value["lineage"]["prior_correction_sha256"] = previous_by_chain.get(chain)
        value["lineage"]["correction_sha256"] = None
        value["lineage"]["correction_sha256"] = _sha256(_canonical_record_bytes(value))
        previous_by_chain[chain] = value["lineage"]["correction_sha256"]
        updated.append(value)
    raw = b"".join(
        (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for value in updated
    )
    (root / "migrations" / "correction-records-v3.jsonl").write_bytes(raw)
    return {
        "record_count": len(updated),
        "before_proofs_recomputed": len(updated),
        "after_proofs_recomputed": sum(1 for _, _, is_final in proof_bindings if is_final),
        "withdrawal_absence_checks": sum(1 for _, _, is_final in proof_bindings if not is_final),
        "previously_mismatched_after_proofs": changed_after,
    }




def _legacy_manifests(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(LEGACY_MANIFESTS):
        try:
            raw = _git_object(root, SOURCE_BASE_SHA, f"migrations/{name}")
        except ManifestValidationError:
            raw = (root / "migrations" / name).read_bytes()
        value = _parse_json(raw)
        if not isinstance(value, dict):
            raise ManifestValidationError("legacy_manifest_invalid")
        result[name] = value
    return result


def expected_manifests_for_bytes(
    root: Path,
    final_raw: bytes,
    *,
    base_raw: Optional[bytes] = None,
    dispositions_raw: Optional[bytes] = None,
    manifest_names: Optional[set[str]] = None,
) -> dict[str, dict[str, Any]]:
    if base_raw is None:
        base_raw = _git_object(root, SOURCE_BASE_SHA, "evaluations.jsonl")
    if dispositions_raw is None:
        dispositions_raw = (root / "ledger" / "dispositions.jsonl").read_bytes()
    base_rows = _records(base_raw)
    candidate_rows = _source_rows(root, SOURCE_CANDIDATE_SHA)
    final_rows = _records(final_raw)
    candidate_subject_by_id = {row["run_id"]: f"subject-{_source_record_sha256(row)}" for row in candidate_rows}
    final_subject_by_id = {row["run_id"]: candidate_subject_by_id[row["run_id"]] for row in final_rows}
    withdrawn, redactions, scores, replacements, removed_subject = _public_bindings(root)
    main_subjects = {
        candidate_subject_by_id[row["run_id"]]
        for row in base_rows
        if row["run_id"] in candidate_subject_by_id
    } | set(withdrawn)
    final_subjects = set(final_subject_by_id.values())
    removed = list(withdrawn)
    preserved = [candidate_subject_by_id[row["run_id"]] for row in final_rows if row["run_id"] in {item["run_id"] for item in base_rows}]
    added = [candidate_subject_by_id[row["run_id"]] for row in final_rows if row["run_id"] not in {item["run_id"] for item in base_rows}]
    correction_raw, correction_records = _load_correction_records(root)
    withdrawal_correction_subjects = [row["target"]["run_id"] for row in correction_records if row["record_type"] == "withdrawal" and row["target"]["record_type"] == "correction"]
    final_correction_subjects = [final_subject_by_id[row["run_id"]] for row in final_rows if row.get("record_type") == "correction" and row["run_id"] in final_subject_by_id]
    withdrawn_correction_ids = withdrawal_correction_subjects
    preserved_correction_ids = [subject for subject in final_correction_subjects if subject in main_subjects]
    correction_manifest = {
        "schema_version": 3,
        "manifest_type": "correction_migration_manifest",
        "generated_at": "2026-08-02T00:00:00+08:00",
        "source_base_sha": SOURCE_BASE_SHA,
        "source_candidate_sha": SOURCE_CANDIDATE_SHA,
        "starting_correction_count": sum(row.get("record_type") == "correction" for row in base_rows),
        "withdrawn_correction_count": len(withdrawn_correction_ids),
        "withdrawn_correction_ids": withdrawn_correction_ids,
        "withdrawn_corrections_sha256": _closed_set_hash(withdrawn_correction_ids),
        "removed_or_folded_correction_count": 1,
        "removed_or_folded_correction_ids": [removed_subject],
        "removed_or_folded_corrections_sha256": _closed_set_hash([removed_subject]),
        "preserved_correction_count": len(preserved_correction_ids),
        "preserved_correction_ids": preserved_correction_ids,
        "preserved_corrections_sha256": _closed_set_hash(preserved_correction_ids),
        "final_correction_count": sum(row.get("record_type") == "correction" for row in final_rows),
        "before_corrections_sha256": _sha256(b"".join(_evaluation_line_bytes(row) for row in base_rows if row.get("record_type") == "correction")),
        "after_corrections_sha256": _sha256(b"".join(_evaluation_line_bytes(row) for row in final_rows if row.get("record_type") == "correction")),
        "correction_record_count": len(correction_records),
        "correction_records_sha256": _sha256(correction_raw),
        "authority_gap_record_count": 59,
        "public_safe_redaction_count": 25,
        "append_only_factual_score_correction_count": 19,
        "withdrawal_count": 10,
        "replacement_count": 3,
        "unchanged_record_count": 22,
        "candidate_record_count": len(final_rows),
        "candidate_evaluations_sha256": _sha256(final_raw),
        "candidate_dispositions_sha256": _sha256(dispositions_raw),
        "generated_output_hashes": TARGET_OUTPUT_HASHES,
        "source_inputs": ["evaluations.jsonl", "migrations/correction-records-v3.jsonl", "migrations/correction-migration-manifest.json", "migrations/base-model-v2.json", "migrations/reasoning-scrub-receipt.json"],
        "generated_files": ["README.md", "scorecard.md", "analysis/model-recommendation.json", "ledger/dispositions.jsonl"],
        "candidate_allowed_files": CANDIDATE_ALLOWED_FILES,
        "terminal_seal_file": "ledger/receipts/batches/batch-20260729-gate3-amendment-004.json",
        "expected_commit_count": 2,
    }
    replacements_list = []
    for removed_id, replacement_id in replacements.items():
        removed_row = next(row for row in correction_records if row["record_type"] == "base_model_replacement" and row["replacement"]["removed_run_id"] == removed_id)
        replacement_sha = next(row["target"]["original_record_sha256"] for row in correction_records if row["target"]["run_id"] == replacement_id and row["record_type"] == "authority_gap")
        replacements_list.append({
            "identity_change": "base_model_identity_only",
            "preserve_unaffected_fields": True,
            "reason": "owner-authorised identity replacement; unaffected fields preserved",
            "removed_record_sha256": removed_row["target"]["original_record_sha256"],
            "removed_run_id": removed_id,
            "replacement_record_sha256": replacement_sha,
            "replacement_run_id": replacement_id,
        })
    base_manifest = {
        "schema_version": 2,
        "manifest_type": "base_model_v2_migration",
        "generated_at": "2026-08-02T00:00:00+08:00",
        "source_base_sha": SOURCE_BASE_SHA,
        "source_candidate_sha": SOURCE_CANDIDATE_SHA,
        "starting_record_count": len(base_rows),
        "withdrawn_records_count": len(removed),
        "withdrawn_records_sha256": _closed_set_hash(removed),
        "withdrawn_record_ids": removed,
        "replacement_count": 3,
        "base_model_replacements": replacements_list,
        "preserved_records_count": len(preserved),
        "preserved_record_ids": preserved,
        "newly_admitted_records_count": len(added),
        "newly_admitted_record_ids": added,
        "final_evaluation_count": sum(row.get("record_type") == "evaluation" for row in final_rows),
        "final_correction_count": sum(row.get("record_type") == "correction" for row in final_rows),
        "final_total_count": len(final_rows),
        "before_sha256": _sha256(base_raw),
        "after_sha256": _sha256(final_raw),
        "preserved_base_sha256": _sha256(b"".join(_evaluation_line_bytes(row) for row in final_rows if final_subject_by_id[row["run_id"]] in set(preserved))),
        "reasoning_only_correction_removed": {"reason": "owner-authorised removal only", "record_sha256": REASONING_REMOVED_RECORD_SHA, "run_id": removed_subject},
    }
    reasoning_manifest = {
        "schema_version": 2,
        "manifest_type": "reasoning_scrub_receipt",
        "generated_at": "2026-08-02T00:00:00+08:00",
        "source_base_sha": SOURCE_BASE_SHA,
        "source_candidate_sha": SOURCE_CANDIDATE_SHA,
        "evaluations_sha256": _sha256(final_raw),
        "scrubbed_fields_count": 73,
        "removed_attribute_key_count": 8,
        "removed_correction_count": 1,
        "removed_corrections_sha256": _closed_set_hash([removed_subject]),
        "removed_correction_ids": [removed_subject],
        "candidate_record_count": len(final_rows),
    }
    manifests = {"base-model-v2.json": base_manifest, "correction-migration-manifest.json": correction_manifest, "historical-direct-controller-bypass-reconciliation.json": _historical_bypass_manifest(), "reasoning-scrub-receipt.json": reasoning_manifest, **_legacy_manifests(root)}
    if manifest_names is None:
        return manifests
    if not set(manifest_names).issubset(manifests):
        raise ManifestValidationError("manifest_universe_invalid")
    return {name: manifests[name] for name in sorted(manifest_names)}

WITHDRAWN_IDS, REDACTION_IDS, SCORE_VALUES, REPLACEMENTS, REASONING_ONLY_REMOVED = _public_bindings(ROOT)


def _locked_historical_final_raw(root: Path) -> bytes:
    """Rebuild the immutable migration result from its locked source authority."""

    _, correction_records = _load_correction_records(root)
    candidate_rows = _source_rows(root, SOURCE_CANDIDATE_SHA)
    score_source_shas = source_bound_public_bindings(root, correction_records)[2]
    final_rows = [
        _effective_record(row, score_source_shas.get(_source_record_sha256(row)))
        for row in candidate_rows
    ]
    return b"".join(_evaluation_line_bytes(row) for row in final_rows)


def _locked_dispositions_raw(root: Path) -> bytes:
    return _git_object(root, SOURCE_CANDIDATE_SHA, "ledger/dispositions.jsonl")


def expected_manifests(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    return expected_manifests_for_bytes(
        root,
        _locked_historical_final_raw(root),
        dispositions_raw=_locked_dispositions_raw(root),
    )


def _schema(root: Path) -> dict[str, Any]:
    try:
        schema = _parse_json((root / "schema" / "manifest.schema.json").read_bytes())
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, ManifestValidationError, jsonschema.SchemaError) as error:
        raise ManifestValidationError("manifest_schema_invalid") from error


def validate_manifest_documents(actual: Mapping[str, Any], expected: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    if set(actual) != set(MANIFEST_PATHS) or set(expected) != set(MANIFEST_PATHS):
        raise ManifestValidationError("manifest_set_mismatch")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for name, manifest_type in MANIFEST_PATHS.items():
        value = actual[name]
        try:
            validator.validate(value)
        except jsonschema.ValidationError as error:
            raise ManifestValidationError("manifest_schema_failure") from error
        if value.get("manifest_type") != manifest_type or value != expected[name]:
            raise ManifestValidationError("manifest_content_mismatch")


def _validated_jsonl(
    root: Path,
    raw: bytes,
    *,
    schema_path: str,
    identity_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if (
        not raw
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise ManifestValidationError("candidate_jsonl_bytes_invalid")
    schema = _parse_json((root / schema_path).read_bytes())
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
    except jsonschema.SchemaError as error:
        raise ManifestValidationError("candidate_schema_invalid") from error
    records: list[dict[str, Any]] = []
    identities: set[tuple[Any, ...]] = set()
    for line in raw.splitlines(keepends=True):
        if line == b"\n" or not line.endswith(b"\n"):
            raise ManifestValidationError("candidate_jsonl_delimiter_invalid")
        try:
            value = json.loads(
                line[:-1].decode("utf-8", errors="strict"),
                object_pairs_hook=_duplicate_rejecting_pairs,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ManifestValidationError("candidate_jsonl_invalid")
        if not isinstance(value, dict) or any(validator.iter_errors(value)):
            raise ManifestValidationError("candidate_record_invalid")
        identity = tuple(value.get(field) for field in identity_fields)
        if identity in identities:
            raise ManifestValidationError("candidate_identity_duplicate")
        identities.add(identity)
        records.append(value)
    return records


def _resolve_base(root: Path, base_ref: str) -> str:
    if not isinstance(base_ref, str) or not re.fullmatch(
        r"[0-9a-f]{40}|[A-Za-z0-9._/-]+",
        base_ref,
    ):
        raise ManifestValidationError("candidate_base_invalid")
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    resolved = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", resolved) is None:
        raise ManifestValidationError("candidate_base_invalid")
    return resolved


def _validate_generated_outputs(
    root: Path,
    evaluation_records: list[dict[str, Any]],
) -> None:
    try:
        from scripts.rebuild_views import expected_files_for_records, resolved_evaluations

        readme_raw = (root / "README.md").read_bytes()
        scorecard_raw = (root / "scorecard.md").read_bytes()
        readme = readme_raw.decode("utf-8", errors="strict")
        scorecard = scorecard_raw.decode("utf-8", errors="strict")
        expected_readme, expected_scorecard, recommendation = expected_files_for_records(
            resolved_evaluations(evaluation_records),
            readme,
            scorecard,
        )
        expected_recommendation = (
            json.dumps(
                recommendation,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if (
            readme_raw != expected_readme.encode("utf-8")
            or scorecard_raw != expected_scorecard.encode("utf-8")
            or (root / "analysis" / "model-recommendation.json").read_bytes()
            != expected_recommendation
        ):
            raise ManifestValidationError("candidate_generated_output_mismatch")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ManifestValidationError("candidate_generated_output_invalid") from error


def _validate_future_candidate(
    root: Path,
    *,
    base_ref: str,
    locked_evaluations: bytes,
    locked_dispositions: bytes,
) -> dict[str, Any]:
    resolved = _resolve_base(root, base_ref)
    base_evaluations = _git_object(root, resolved, "evaluations.jsonl")
    base_dispositions = _git_object(root, resolved, "ledger/dispositions.jsonl")
    candidate_evaluations = (root / "evaluations.jsonl").read_bytes()
    candidate_dispositions = (root / "ledger" / "dispositions.jsonl").read_bytes()
    if (
        not base_evaluations.startswith(locked_evaluations)
        or not candidate_evaluations.startswith(base_evaluations)
        or not base_dispositions.startswith(locked_dispositions)
        or not candidate_dispositions.startswith(base_dispositions)
    ):
        raise ManifestValidationError("candidate_append_only_prefix_mismatch")
    base_evaluation_records = _validated_jsonl(
        root,
        base_evaluations,
        schema_path="schema/evaluation.schema.json",
        identity_fields=("run_id",),
    )
    candidate_evaluation_records = _validated_jsonl(
        root,
        candidate_evaluations,
        schema_path="schema/evaluation.schema.json",
        identity_fields=("run_id",),
    )
    base_disposition_records = _validated_jsonl(
        root,
        base_dispositions,
        schema_path="schema/disposition.schema.json",
        identity_fields=("comment_id", "comment_body_sha256"),
    )
    candidate_disposition_records = _validated_jsonl(
        root,
        candidate_dispositions,
        schema_path="schema/disposition.schema.json",
        identity_fields=("comment_id", "comment_body_sha256"),
    )
    _validate_generated_outputs(root, candidate_evaluation_records)
    return {
        "mode": "future_append_only",
        "base_sha": resolved,
        "appended_evaluations": len(candidate_evaluation_records)
        - len(base_evaluation_records),
        "appended_dispositions": len(candidate_disposition_records)
        - len(base_disposition_records),
    }

def _contains_historical_run_id(value: Any, run_ids: frozenset[str]) -> bool:
    if isinstance(value, str):
        return value in run_ids
    if isinstance(value, dict):
        return any(_contains_historical_run_id(child, run_ids) for child in value.values())
    if isinstance(value, list):
        return any(_contains_historical_run_id(child, run_ids) for child in value)
    return False


def _historical_bypass_jsonl_values(raw: bytes) -> list[Any]:
    values: list[Any] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            values.append(
                json.loads(
                    line.decode("utf-8", errors="strict"),
                    object_pairs_hook=_duplicate_rejecting_pairs,
                    parse_constant=_reject_constant,
                )
            )
        except (UnicodeDecodeError, ValueError):
            raise ManifestValidationError("historical_bypass_evidence_invalid")
    return values


def _historical_bypass_receipt_scan(root: Path) -> None:
    receipts_root = root / "ledger" / "receipts"
    if not receipts_root.exists():
        raise ManifestValidationError("historical_bypass_receipts_unavailable")
    for path in receipts_root.rglob("*.json"):
        try:
            value = _parse_json(path.read_bytes())
        except (OSError, ManifestValidationError):
            raise ManifestValidationError("historical_bypass_receipt_invalid")
        if _contains_historical_run_id(value, HISTORICAL_BYPASS_RUN_IDS):
            raise ManifestValidationError("historical_bypass_receipt_present")


def _historical_bypass_first_commit_check(root: Path, entry: Mapping[str, Any], line: bytes) -> None:
    commit = entry["canonical_entry_commit_sha"]
    committed_raw = _git_object(root, commit, "evaluations.jsonl")
    committed_lines = [candidate for candidate in committed_raw.splitlines(keepends=True) if candidate.strip()]
    if sum(candidate == line for candidate in committed_lines) != 1:
        raise ManifestValidationError("historical_bypass_commit_record_mismatch")
    result = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", commit],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    parents = result.stdout.strip().split()
    if result.returncode != 0 or len(parents) != 2 or parents[0] != commit:
        raise ManifestValidationError("historical_bypass_commit_topology_invalid")
    parent_raw = _git_object(root, parents[1], "evaluations.jsonl")
    if any(candidate == line for candidate in parent_raw.splitlines(keepends=True)):
        raise ManifestValidationError("historical_bypass_not_first_commit")


def _validate_historical_bypass_authority(
    root: Path,
    final_raw: bytes,
    dispositions_raw: bytes,
    actual_manifest: Mapping[str, Any],
) -> None:
    expected = _historical_bypass_manifest()
    if dict(actual_manifest) != expected:
        raise ManifestValidationError("historical_bypass_manifest_mismatch")
    if expected["canonical_base_sha"] != "d38852a98b630bf1bd39ce62bf8e5d1e2921f39d":
        raise ManifestValidationError("historical_bypass_base_mismatch")
    canonical_raw = _git_object(root, expected["canonical_base_sha"], "evaluations.jsonl")
    canonical_dispositions = _git_object(root, expected["canonical_base_sha"], "ledger/dispositions.jsonl")
    records = _records(canonical_raw)
    lines = [line for line in canonical_raw.splitlines(keepends=True) if line.strip()]
    if len(records) != len(lines):
        raise ManifestValidationError("historical_bypass_line_binding_invalid")
    for entry in HISTORICAL_BYPASS_ENTRIES:
        matching = [
            (record, line)
            for record, line in zip(records, lines)
            if record.get("run_id") == entry["evaluation_run_id"]
        ]
        if len(matching) != 1:
            raise ManifestValidationError("historical_bypass_duplicate_or_missing_row")
        record, line = matching[0]
        if _sha256(line) != entry["canonical_record_sha256"] or not line.endswith(b"\n"):
            raise ManifestValidationError("historical_bypass_raw_line_hash_mismatch")
        if not isinstance(record, dict) or record.get("run_id") != entry["evaluation_run_id"]:
            raise ManifestValidationError("historical_bypass_identity_mismatch")
        _historical_bypass_first_commit_check(root, entry, line)
    if len({entry["evaluation_run_id"] for entry in HISTORICAL_BYPASS_ENTRIES}) != 6:
        raise ManifestValidationError("historical_bypass_entry_count_invalid")
    if _contains_historical_run_id(_historical_bypass_jsonl_values(canonical_dispositions), HISTORICAL_BYPASS_RUN_IDS):
        raise ManifestValidationError("historical_bypass_disposition_present")
    _historical_bypass_receipt_scan(root)


def validate_all(
    root: Path = ROOT,
    *,
    base_ref: Optional[str] = None,
) -> dict[str, Any]:
    locked_evaluations = _locked_historical_final_raw(root)
    locked_dispositions = _locked_dispositions_raw(root)
    expected = expected_manifests(root)
    actual: dict[str, Any] = {}
    try:
        for name in MANIFEST_PATHS:
            raw = (root / "migrations" / name).read_bytes()
            value = _parse_json(raw)
            if _canonical_json_bytes(value) != raw:
                raise ManifestValidationError("manifest_noncanonical_bytes")
            actual[name] = value
    except (OSError, ManifestValidationError):
        raise ManifestValidationError("manifest_unavailable")
    validate_manifest_documents(actual, expected, _schema(root))
    _validate_historical_bypass_authority(
        root,
        locked_evaluations,
        locked_dispositions,
        actual[HISTORICAL_BYPASS_MANIFEST_PATH],
    )
    correction_evidence = validate_correction_records(
        root,
        final_raw=locked_evaluations,
    )
    evaluations_raw = (root / "evaluations.jsonl").read_bytes()
    dispositions_raw = (root / "ledger" / "dispositions.jsonl").read_bytes()
    if (
        _sha256(evaluations_raw) == TARGET_EVALUATIONS_SHA
        and _sha256(dispositions_raw) == TARGET_DISPOSITIONS_SHA
    ):
        evaluation_records = _validated_jsonl(
            root,
            evaluations_raw,
            schema_path="schema/evaluation.schema.json",
            identity_fields=("run_id",),
        )
        _validated_jsonl(
            root,
            dispositions_raw,
            schema_path="schema/disposition.schema.json",
            identity_fields=("comment_id", "comment_body_sha256"),
        )
        for relative_path, expected_hash in TARGET_OUTPUT_HASHES.items():
            if _sha256((root / relative_path).read_bytes()) != expected_hash:
                raise ManifestValidationError("candidate_generated_output_hash_mismatch")
        _validate_generated_outputs(root, evaluation_records)
        candidate_evidence = {
            "mode": "unchanged_canonical_head",
            "appended_evaluations": 0,
            "appended_dispositions": 0,
        }
    else:
        if base_ref is None:
            raise ManifestValidationError("candidate_base_required")
        candidate_evidence = _validate_future_candidate(
            root,
            base_ref=base_ref,
            locked_evaluations=locked_evaluations,
            locked_dispositions=locked_dispositions,
        )
    return {
        "manifest_count": len(actual),
        "final_total_count": expected["base-model-v2.json"]["final_total_count"],
        "evaluations_sha256": expected["base-model-v2.json"]["after_sha256"],
        "correction_records": correction_evidence,
        "candidate": candidate_evidence,
    }


def write_all(root: Path = ROOT) -> None:
    expected = expected_manifests(root)
    for name in G3_MANIFESTS:
        (root / "migrations" / name).write_bytes(_canonical_json_bytes(expected[name]))


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    import argparse

    parser = argparse.ArgumentParser(prog="validate_manifests")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--base-ref")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rewrite-correction-proofs", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        if args.rewrite_correction_proofs:
            rewrite_correction_proofs(args.repository_root)
        if args.write:
            write_all(args.repository_root)
        evidence = validate_all(args.repository_root, base_ref=args.base_ref)
    except ManifestValidationError:
        print("Manifest validation failed.", file=sys.stderr)
        return 1
    print(f"Manifest validation passed: {evidence['manifest_count']} closed manifests, {evidence['final_total_count']} final records, {evidence['correction_records']['record_count']} v3 correction records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
