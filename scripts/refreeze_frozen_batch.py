#!/usr/bin/env python3
"""Correct candidate artifacts from the exact live frozen Unicode source."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.processor.common import ProcessorError, canonical_json_line_bytes
from scripts.processor.frozen_source import refetch_frozen_source
from scripts.processor.intake_parser import (
    INTAKE_MARKER,
    INTAKE_VALIDATOR,
    adapt_historical_payload,
    canonical_record_from_payload,
)

RECEIPT_PATH = (
    ROOT
    / "ledger"
    / "receipts"
    / "batches"
    / "batch-20260729-gate3-amendment-004.json"
)


def refreeze(root: Path = ROOT) -> dict[str, int]:
    receipt_path = (
        root
        / "ledger"
        / "receipts"
        / "batches"
        / "batch-20260729-gate3-amendment-004.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence = refetch_frozen_source(root, receipt)
    old_hashes = receipt.get("source_body_sha256", {})
    changed_ids = [
        int(comment_id)
        for comment_id, digest in evidence["source_body_sha256"].items()
        if old_hashes.get(comment_id) != digest
    ]
    if len(changed_ids) != 1:
        raise ProcessorError("source_changed")

    terminal = receipt.get("terminal_outcomes", {})
    changed_records: dict[str, dict] = {}
    changed_record_fields: dict[str, dict] = {}
    changed_dispositions: dict[int, str] = {}
    comments = {comment["id"]: comment for comment in evidence["comments"]}
    for comment_id in changed_ids:
        outcome = terminal.get(str(comment_id))
        if not isinstance(outcome, dict):
            raise ProcessorError("source_changed")
        if outcome.get("outcome_code") == "admitted":
            body = comments[comment_id]["body"]
            if not isinstance(body, str) or not body.startswith(INTAKE_MARKER):
                raise ProcessorError("source_changed")
            raw = body[len(INTAKE_MARKER):].lstrip(" \t\r\n")
            try:
                payload, end = json.JSONDecoder().raw_decode(raw)
            except (TypeError, ValueError):
                raise ProcessorError("source_changed")
            if not isinstance(payload, dict) or raw[end:].strip():
                raise ProcessorError("source_changed")
            adapted = adapt_historical_payload(payload)
            if not adapted:
                raise ProcessorError("source_changed")
            expected_run_id = outcome.get("evaluation_run_id")
            if adapted.get("evaluation_run_id") != expected_run_id:
                raise ProcessorError("source_changed")
            intake_errors = list(INTAKE_VALIDATOR.iter_errors(adapted))
            if not intake_errors:
                record = canonical_record_from_payload(adapted)
                changed_records[record["run_id"]] = record
            elif comment_id == 5086781596:
                evidence_value = payload.get("public_safe_evidence")
                defects = (
                    evidence_value.get("verified_defects")
                    if isinstance(evidence_value, dict)
                    else None
                )
                non_ascii = [
                    ord(char)
                    for item in defects
                    for char in item
                    if ord(char) > 127
                ] if isinstance(defects, list) and all(
                    isinstance(item, str) for item in defects
                ) else []
                if non_ascii != [8212, 8212]:
                    raise ProcessorError("source_changed")
                changed_record_fields[expected_run_id] = {
                    "verified_defects": defects,
                }
            else:
                raise ProcessorError("source_changed")
        else:
            changed_dispositions[comment_id] = evidence["source_body_sha256"][
                str(comment_id)
            ]

    evaluation_lines = []
    replaced_records = 0
    for line in (root / "evaluations.jsonl").read_bytes().splitlines(keepends=True):
        record = json.loads(line.decode("utf-8"))
        replacement = changed_records.get(record.get("run_id"))
        if replacement is not None:
            evaluation_lines.append(canonical_json_line_bytes(replacement))
            replaced_records += 1
        elif record.get("run_id") in changed_record_fields:
            record.update(changed_record_fields[record["run_id"]])
            evaluation_lines.append(canonical_json_line_bytes(record))
            replaced_records += 1
        else:
            evaluation_lines.append(line)
    if replaced_records != len(changed_records) + len(changed_record_fields):
        raise ProcessorError("source_changed")
    (root / "evaluations.jsonl").write_bytes(b"".join(evaluation_lines))

    disposition_lines = []
    replaced_dispositions = 0
    for line in (root / "ledger" / "dispositions.jsonl").read_bytes().splitlines(keepends=True):
        disposition = json.loads(line.decode("utf-8"))
        comment_id = disposition.get("comment_id")
        if comment_id in changed_dispositions:
            disposition["comment_body_sha256"] = changed_dispositions[comment_id]
            disposition_lines.append(canonical_json_line_bytes(disposition))
            replaced_dispositions += 1
        else:
            disposition_lines.append(line)
    if replaced_dispositions != len(changed_dispositions):
        raise ProcessorError("source_changed")
    (root / "ledger" / "dispositions.jsonl").write_bytes(
        b"".join(disposition_lines)
    )
    return {
        "membership_count": len(evidence["fingerprints"]),
        "changed_comment_count": len(changed_ids),
        "changed_record_count": replaced_records,
        "changed_disposition_count": replaced_dispositions,
        "later_comment_count": evidence["later_comment_count"],
    }


def main() -> int:
    try:
        evidence = refreeze(ROOT)
    except (OSError, UnicodeDecodeError, ValueError, ProcessorError):
        print("Frozen source correction failed.", file=sys.stderr)
        return 1
    print(
        "Frozen source correction passed: "
        f"{evidence['membership_count']} members, "
        f"{evidence['changed_comment_count']} corrected hash, "
        f"{evidence['changed_record_count']} record change, "
        f"{evidence['changed_disposition_count']} disposition change, "
        f"{evidence['later_comment_count']} later comments excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
