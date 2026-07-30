#!/usr/bin/env python3
"""Migrate the one frozen draft receipt to a private-safe v2 content seal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.processor.common import validate_batch_receipt_closure
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    _record_lines,
    git_object_bytes,
    resolve_commit,
    sha256_bytes,
)

FROZEN_BATCH_ID = "batch-20260729-gate3-amendment-004"
FROZEN_WATERMARK = 5115014307
FROZEN_COUNT = 101
FROZEN_LATEST_UPDATE = "2026-07-29T08:23:28Z"
FROZEN_SNAPSHOT = "eac871f9ec34e37346bd9c83d8af2f8b1d5796ff4f72315d15966d49edf554ef"


def _legacy_receipt(root: Path, content_sha: str, batch_id: str) -> dict[str, Any]:
    raw = git_object_bytes(
        root,
        content_sha,
        f"ledger/receipts/batches/{batch_id}.json",
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ReceiptValidationError("seal_legacy_receipt_invalid")
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("receipt_type") != "batch"
        or value.get("batch_id") != batch_id
    ):
        raise ReceiptValidationError("seal_legacy_receipt_invalid")
    return value


def build_sealed_receipt(
    root: Path,
    *,
    candidate_content_commit_sha: str,
    batch_id: str = FROZEN_BATCH_ID,
) -> dict[str, Any]:
    content_sha = resolve_commit(root, candidate_content_commit_sha)
    legacy = _legacy_receipt(root, content_sha, batch_id)
    if batch_id != FROZEN_BATCH_ID:
        raise ReceiptValidationError("seal_unauthorised_batch")
    if (
        legacy.get("source_comment_watermark") != FROZEN_WATERMARK
        or legacy.get("full_queue_count") != FROZEN_COUNT
        or legacy.get("latest_observed_update_time") != FROZEN_LATEST_UPDATE
        or legacy.get("queue_snapshot_sha256") != FROZEN_SNAPSHOT
    ):
        raise ReceiptValidationError("seal_frozen_authority_mismatch")

    source_ids = legacy.get("source_comment_ids")
    source_hashes = legacy.get("source_body_sha256")
    legacy_bindings = legacy.get("comment_bindings")
    if (
        not isinstance(source_ids, list)
        or source_ids != sorted(source_ids)
        or len(source_ids) != FROZEN_COUNT
        or len(set(source_ids)) != FROZEN_COUNT
        or not isinstance(source_hashes, dict)
        or set(source_hashes) != {str(comment_id) for comment_id in source_ids}
        or not isinstance(legacy_bindings, list)
    ):
        raise ReceiptValidationError("seal_frozen_membership_mismatch")
    by_comment = {
        binding.get("comment_id"): binding
        for binding in legacy_bindings
        if isinstance(binding, dict)
    }
    if set(by_comment) != set(source_ids) or len(by_comment) != len(legacy_bindings):
        raise ReceiptValidationError("seal_frozen_binding_mismatch")

    records = _record_lines(
        git_object_bytes(root, content_sha, CANONICAL_PATHS["evaluations_jsonl"])
    )
    terminal_outcomes: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, Any]] = []
    admitted_run_ids: list[str] = []
    record_hashes: dict[str, str] = {}
    record_proofs: dict[str, dict[str, Any]] = {}
    for comment_id in source_ids:
        source = by_comment[comment_id]
        classification = source.get("classification")
        run_id = source.get("evaluation_run_id")
        if classification == "admitted":
            if not isinstance(run_id, str) or run_id not in records:
                raise ReceiptValidationError("seal_admitted_record_missing")
            line, record = records[run_id]
            outcome_code = "admitted"
            record_hash = sha256_bytes(line)
            admitted_run_ids.append(run_id)
            record_hashes[run_id] = record_hash
            record_proofs[run_id] = {
                "provider": record.get("provider"),
                "model": record.get("model"),
                "outcome": record.get("outcome"),
                "weighted_score_5": record.get("weighted_score_5"),
            }
        elif classification == "terminal" and source.get("terminal_disposition") == "no_marker":
            outcome_code = "no_marker"
            run_id = None
            record_hash = None
        elif classification == "terminal" and source.get("terminal_disposition") == "owner_withdrawn":
            outcome_code = "withdrawn_identity"
            run_id = None
            record_hash = None
        elif classification == "pending" and source.get("pending_reason_code") == "PENDING_CONTROLLER_ACTION":
            outcome_code = "authority_missing"
            run_id = None
            record_hash = None
        else:
            raise ReceiptValidationError("seal_unknown_legacy_outcome")
        outcome = {
            "outcome_code": outcome_code,
            "evaluation_run_id": run_id,
            "canonical_record_sha256": record_hash,
            "cleanup_eligible": source.get("cleanup_eligible") is True,
        }
        terminal_outcomes[str(comment_id)] = outcome
        bindings.append(
            {
                "comment_id": comment_id,
                "created_at": source.get("created_at"),
                "updated_at": source.get("updated_at"),
                "body_sha256": source_hashes[str(comment_id)],
                **outcome,
            }
        )
    if len(admitted_run_ids) != len(set(admitted_run_ids)):
        raise ReceiptValidationError("seal_duplicate_admitted_record")

    canonical_hashes = {
        hash_name: sha256_bytes(git_object_bytes(root, content_sha, relative_path))
        for hash_name, relative_path in CANONICAL_PATHS.items()
    }
    receipt = {
        "schema_version": 2,
        "receipt_type": "batch",
        "batch_id": batch_id,
        "batch_mode": legacy.get("batch_mode", "initial"),
        "controller_run_id": legacy.get("controller_run_id"),
        "base_sha": legacy.get("base_sha"),
        "canonical_main_sha": legacy.get("base_sha"),
        "candidate_content_commit_sha": content_sha,
        "pr_number": legacy.get("pr_number"),
        "source_issue_number": 142,
        "receipt_issue_number": 143,
        "source_comment_watermark": FROZEN_WATERMARK,
        "full_queue_count": FROZEN_COUNT,
        "latest_observed_comment_id": max(source_ids),
        "latest_observed_update_time": FROZEN_LATEST_UPDATE,
        "queue_snapshot_sha256": FROZEN_SNAPSHOT,
        "source_comment_ids": source_ids,
        "source_body_sha256": source_hashes,
        "selected_comment_ids": source_ids,
        "selected_comment_count": FROZEN_COUNT,
        "terminal_outcome_count": FROZEN_COUNT,
        "terminal_outcomes": terminal_outcomes,
        "admitted_run_ids": admitted_run_ids,
        "accepted_record_proofs": record_proofs,
        "canonical_record_hashes": record_hashes,
        "canonical_hashes": canonical_hashes,
        "comment_bindings": bindings,
    }
    schema = json.loads(
        (root / "schema" / "receipt.schema.json").read_text(encoding="utf-8")
    )
    try:
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(receipt)
    except jsonschema.ValidationError:
        raise ReceiptValidationError("seal_schema_failure")
    if not validate_batch_receipt_closure(receipt):
        raise ReceiptValidationError("seal_closure_failure")
    return receipt


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="seal_batch_receipt")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--candidate-content-commit-sha", required=True)
    parser.add_argument("--batch-id", default=FROZEN_BATCH_ID)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        receipt = build_sealed_receipt(
            args.repository_root,
            candidate_content_commit_sha=args.candidate_content_commit_sha,
            batch_id=args.batch_id,
        )
        path = (
            args.repository_root
            / "ledger"
            / "receipts"
            / "batches"
            / f"{args.batch_id}.json"
        )
        path.write_bytes(
            (
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            ).encode("utf-8")
        )
    except (OSError, ValueError, ReceiptValidationError):
        print("Batch receipt sealing failed.", file=sys.stderr)
        return 1
    print(f"Sealed batch receipt for {args.batch_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
