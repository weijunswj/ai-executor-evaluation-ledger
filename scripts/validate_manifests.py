#!/usr/bin/env python3
"""Rebuild or validate every closed migration/preservation manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_BASE_SHA = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
MANIFEST_PATHS = {
    "base-model-v2.json": "base_model_v2_migration",
    "correction-migration-manifest.json": "correction_migration_manifest",
    "evaluation-protocol-v1.json": "evaluation_protocol_v1",
    "historical-intake-adapter-manifest.json": "historical_intake_adapter_manifest",
    "preservation-manifest.json": "canonical_base_preservation_manifest",
    "reasoning-scrub-receipt.json": "reasoning_scrub_receipt",
}


class ManifestValidationError(RuntimeError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _closed_set_hash(values: list[str]) -> str:
    payload = (
        json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return _sha256(payload)


def _git_object(root: Path, revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        raise ManifestValidationError("manifest_base_unavailable")
    return result.stdout


def _records(raw: bytes) -> list[dict[str, Any]]:
    try:
        decoded = raw.decode("utf-8", errors="strict")
        records = [json.loads(line) for line in decoded.splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError):
        raise ManifestValidationError("manifest_records_invalid")
    if not all(isinstance(record, dict) for record in records):
        raise ManifestValidationError("manifest_records_invalid")
    return records


def _record_lines(raw: bytes) -> dict[str, bytes]:
    lines: dict[str, bytes] = {}
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            record = json.loads(line.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, ValueError):
            raise ManifestValidationError("manifest_records_invalid")
        run_id = record.get("run_id") if isinstance(record, dict) else None
        if not isinstance(run_id, str) or run_id in lines:
            raise ManifestValidationError("manifest_records_invalid")
        lines[run_id] = line
    return lines


def expected_manifests(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    from scripts.processor.common import MODEL_ALIASES, REASONING_KEYS
    from scripts.processor.intake_parser import LEGACY_ALIAS_PAIRS, VERDICT_VALUES
    from scripts.scrub_identity_variants import legacy_identity_renames

    base_raw = _git_object(root, SOURCE_BASE_SHA, "evaluations.jsonl")
    final_raw = (root / "evaluations.jsonl").read_bytes()
    base = _records(base_raw)
    final = _records(final_raw)
    base_lines = _record_lines(base_raw)
    final_lines = _record_lines(final_raw)
    renames = legacy_identity_renames()
    base_by_id = {
        renames.get(record["run_id"], record["run_id"]): record
        for record in base
    }
    final_by_id = {record["run_id"]: record for record in final}
    if len(base_by_id) != len(base) or len(final_by_id) != len(final):
        raise ManifestValidationError("manifest_records_invalid")

    removed_ids = sorted(set(base_by_id) - set(final_by_id))
    withdrawn_ids = sorted(
        run_id
        for run_id in removed_ids
        if base_by_id[run_id].get("provider") == "Anthropic"
    )
    folded_ids = sorted(set(removed_ids) - set(withdrawn_ids))
    preserved_ids = sorted(set(base_by_id).intersection(final_by_id))
    newly_admitted_ids = sorted(set(final_by_id) - set(base_by_id))
    if (
        len(withdrawn_ids) != 6
        or len(folded_ids) != 1
        or len(preserved_ids) != 59
    ):
        raise ManifestValidationError("manifest_migration_boundary_changed")

    final_evaluations = [
        record for record in final if record.get("record_type") == "evaluation"
    ]
    final_corrections = [
        record for record in final if record.get("record_type") == "correction"
    ]
    base_corrections = [
        record for record in base if record.get("record_type") == "correction"
    ]
    preserved_corrections = [
        record["run_id"]
        for record in final_corrections
        if record["run_id"] in base_by_id
    ]
    withdrawn_corrections = [
        run_id
        for run_id in withdrawn_ids
        if base_by_id[run_id].get("record_type") == "correction"
    ]
    folded_corrections = [
        run_id
        for run_id in folded_ids
        if base_by_id[run_id].get("record_type") == "correction"
    ]
    generated_at = max(str(record["reviewed_at"]) for record in final)
    before_hash = _sha256(base_raw)
    after_hash = _sha256(final_raw)
    preserved_bytes = b"".join(
        final_lines[renames.get(record["run_id"], record["run_id"])]
        for record in final
        if record["run_id"] in set(preserved_ids)
    )
    base_correction_bytes = b"".join(
        base_lines[record["run_id"]] for record in base_corrections
    )
    final_correction_bytes = b"".join(
        final_lines[record["run_id"]] for record in final_corrections
    )
    scrubbed_fields_count = sum(
        int(key in record)
        + (
            int(key in record.get("corrected_fields", {}))
            if isinstance(record.get("corrected_fields"), dict)
            else 0
        )
        for record in base
        for key in REASONING_KEYS
    )
    protocol_counts = Counter(
        str(record["evaluation_protocol"]) for record in final_evaluations
    )

    common_counts = {
        "source_base_sha": SOURCE_BASE_SHA,
        "starting_record_count": len(base),
        "withdrawn_records_count": len(withdrawn_ids),
        "withdrawn_records_sha256": _closed_set_hash(withdrawn_ids),
        "removed_or_folded_corrections_count": len(folded_ids),
        "removed_or_folded_corrections_sha256": _closed_set_hash(folded_ids),
        "preserved_records_count": len(preserved_ids),
        "newly_admitted_records_count": len(newly_admitted_ids),
        "final_evaluation_count": len(final_evaluations),
        "final_correction_count": len(final_corrections),
        "final_total_count": len(final),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
    }
    manifests = {
        "base-model-v2.json": {
            "schema_version": 1,
            "manifest_type": "base_model_v2_migration",
            "generated_at": generated_at,
            **common_counts,
            "preserved_base_sha256": _sha256(preserved_bytes),
        },
        "correction-migration-manifest.json": {
            "schema_version": 1,
            "manifest_type": "correction_migration_manifest",
            "generated_at": generated_at,
            "source_base_sha": SOURCE_BASE_SHA,
            "starting_correction_count": len(base_corrections),
            "withdrawn_correction_count": len(withdrawn_corrections),
            "withdrawn_corrections_sha256": _closed_set_hash(withdrawn_corrections),
            "removed_or_folded_correction_count": len(folded_corrections),
            "removed_or_folded_corrections_sha256": _closed_set_hash(folded_corrections),
            "preserved_correction_count": len(preserved_corrections),
            "preserved_corrections_sha256": _closed_set_hash(preserved_corrections),
            "final_correction_count": len(final_corrections),
            "before_corrections_sha256": _sha256(base_correction_bytes),
            "after_corrections_sha256": _sha256(final_correction_bytes),
        },
        "evaluation-protocol-v1.json": {
            "schema_version": 1,
            "manifest_type": "evaluation_protocol_v1",
            "generated_at": generated_at,
            "evaluations_sha256": after_hash,
            "total_evaluations": len(final_evaluations),
            "protocol_counts": dict(sorted(protocol_counts.items())),
            "records": {
                record["run_id"]: record["evaluation_protocol"]
                for record in sorted(final_evaluations, key=lambda item: item["run_id"])
            },
        },
        "historical-intake-adapter-manifest.json": {
            "schema_version": 1,
            "manifest_type": "historical_intake_adapter_manifest",
            "generated_at": generated_at,
            "source_base_sha": SOURCE_BASE_SHA,
            "evaluations_sha256": after_hash,
            "final_total_count": len(final),
            "field_aliases": [
                {
                    "destination_field": destination,
                    "source_field": source,
                }
                for destination, source in LEGACY_ALIAS_PAIRS
            ],
            "model_aliases": dict(sorted(MODEL_ALIASES.items())),
            "accepted_verdict_values": sorted(VERDICT_VALUES),
        },
        "preservation-manifest.json": {
            "schema_version": 1,
            "manifest_type": "canonical_base_preservation_manifest",
            "generated_at": generated_at,
            **common_counts,
        },
        "reasoning-scrub-receipt.json": {
            "schema_version": 1,
            "manifest_type": "reasoning_scrub_receipt",
            "generated_at": generated_at,
            "source_base_sha": SOURCE_BASE_SHA,
            "evaluations_sha256": after_hash,
            "scrubbed_fields_count": scrubbed_fields_count,
            "removed_attribute_key_count": len(REASONING_KEYS),
            "removed_correction_count": len(folded_corrections),
            "removed_corrections_sha256": _closed_set_hash(folded_corrections),
        },
    }
    return manifests


def _schema(root: Path) -> dict[str, Any]:
    try:
        schema = json.loads(
            (root / "schema" / "manifest.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, ValueError, jsonschema.SchemaError):
        raise ManifestValidationError("manifest_schema_invalid")


def validate_manifest_documents(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    if set(actual) != set(MANIFEST_PATHS) or set(expected) != set(MANIFEST_PATHS):
        raise ManifestValidationError("manifest_set_mismatch")
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    for name, manifest_type in MANIFEST_PATHS.items():
        value = actual[name]
        try:
            validator.validate(value)
        except jsonschema.ValidationError as error:
            raise ManifestValidationError("manifest_schema_failure") from error
        if value.get("manifest_type") != manifest_type:
            raise ManifestValidationError("manifest_type_mismatch")
        if value != expected[name]:
            raise ManifestValidationError("manifest_content_mismatch")


def validate_all(root: Path = ROOT) -> dict[str, Any]:
    expected = expected_manifests(root)
    actual: dict[str, Any] = {}
    try:
        for name in MANIFEST_PATHS:
            actual[name] = json.loads(
                (root / "migrations" / name).read_text(encoding="utf-8")
            )
    except (OSError, UnicodeDecodeError, ValueError):
        raise ManifestValidationError("manifest_unavailable")
    validate_manifest_documents(actual, expected, _schema(root))
    return {
        "manifest_count": len(actual),
        "final_total_count": expected["preservation-manifest.json"]["final_total_count"],
        "evaluations_sha256": expected["preservation-manifest.json"]["after_sha256"],
    }


def write_all(root: Path = ROOT) -> None:
    expected = expected_manifests(root)
    for name, value in expected.items():
        (root / "migrations" / name).write_bytes(
            (
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            ).encode("utf-8")
        )


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="validate_manifests")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        if args.write:
            write_all(args.repository_root)
        evidence = validate_all(args.repository_root)
    except ManifestValidationError:
        print("Manifest validation failed.", file=sys.stderr)
        return 1
    print(
        "Manifest validation passed: "
        f"{evidence['manifest_count']} closed manifests, "
        f"{evidence['final_total_count']} final records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
