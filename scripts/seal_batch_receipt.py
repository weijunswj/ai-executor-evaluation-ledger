#!/usr/bin/env python3
"""Seal the frozen batch against exact live UTF-8 and candidate bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.processor.common import validate_batch_receipt_closure
from scripts.processor.frozen_source import (
    FROZEN_BATCH_ID,
    FROZEN_COUNT,
    FROZEN_WATERMARK,
    refetch_frozen_source,
)
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    _record_lines,
    git_object_bytes,
    resolve_commit,
    sha256_bytes,
)


def _source_receipt(root: Path, content_sha: str, batch_id: str) -> dict[str, Any]:
    raw = git_object_bytes(
        root,
        content_sha,
        f"ledger/receipts/batches/{batch_id}.json",
    )
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError):
        raise ReceiptValidationError("seal_source_receipt_invalid")
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 2
        or value.get("receipt_type") != "batch"
        or value.get("batch_id") != batch_id
    ):
        raise ReceiptValidationError("seal_source_receipt_invalid")
    return value


def build_sealed_receipt(
    root: Path,
    *,
    candidate_content_commit_sha: str,
    batch_id: str = FROZEN_BATCH_ID,
    source_reader: Callable[
        [Path, Mapping[str, Any]], Mapping[str, Any]
    ] = refetch_frozen_source,
) -> dict[str, Any]:
    content_sha = resolve_commit(root, candidate_content_commit_sha)
    source = _source_receipt(root, content_sha, batch_id)
    if (
        batch_id != FROZEN_BATCH_ID
        or source.get("source_comment_watermark") != FROZEN_WATERMARK
        or source.get("full_queue_count") != FROZEN_COUNT
    ):
        raise ReceiptValidationError("seal_frozen_authority_mismatch")
    live = source_reader(root, source)
    fingerprints = live.get("fingerprints")
    source_hashes = live.get("source_body_sha256")
    snapshot_hash = live.get("queue_snapshot_sha256")
    if (
        not isinstance(fingerprints, list)
        or len(fingerprints) != FROZEN_COUNT
        or not isinstance(source_hashes, dict)
        or not isinstance(snapshot_hash, str)
    ):
        raise ReceiptValidationError("seal_frozen_source_invalid")

    records = _record_lines(
        git_object_bytes(root, content_sha, CANONICAL_PATHS["evaluations_jsonl"])
    )
    terminal_source = source.get("terminal_outcomes")
    source_ids = source.get("source_comment_ids")
    if not isinstance(terminal_source, dict) or not isinstance(source_ids, list):
        raise ReceiptValidationError("seal_frozen_membership_mismatch")
    fingerprints_by_id = {item.get("id"): item for item in fingerprints}
    if set(fingerprints_by_id) != set(source_ids):
        raise ReceiptValidationError("seal_frozen_membership_mismatch")

    terminal_outcomes: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, Any]] = []
    admitted_run_ids: list[str] = []
    record_hashes: dict[str, str] = {}
    record_proofs: dict[str, dict[str, Any]] = {}
    for comment_id in source_ids:
        prior = terminal_source.get(str(comment_id))
        fingerprint = fingerprints_by_id.get(comment_id)
        if not isinstance(prior, dict) or not isinstance(fingerprint, dict):
            raise ReceiptValidationError("seal_frozen_binding_mismatch")
        run_id = prior.get("evaluation_run_id")
        if run_id is not None:
            if not isinstance(run_id, str) or run_id not in records:
                raise ReceiptValidationError("seal_admitted_record_missing")
            line, record = records[run_id]
            record_hash = sha256_bytes(line)
            admitted_run_ids.append(run_id)
            record_hashes[run_id] = record_hash
            record_proofs[run_id] = {
                "provider": record.get("provider"),
                "model": record.get("model"),
                "outcome": record.get("outcome"),
                "weighted_score_5": record.get("weighted_score_5"),
            }
        else:
            record_hash = None
        outcome = {
            "outcome_code": prior.get("outcome_code"),
            "evaluation_run_id": run_id,
            "canonical_record_sha256": record_hash,
            "cleanup_eligible": prior.get("cleanup_eligible") is True,
        }
        terminal_outcomes[str(comment_id)] = outcome
        bindings.append(
            {
                "comment_id": comment_id,
                "created_at": fingerprint.get("created_at"),
                "updated_at": fingerprint.get("updated_at"),
                "body_sha256": fingerprint.get("body_sha256"),
                **outcome,
            }
        )
    if len(admitted_run_ids) != len(set(admitted_run_ids)):
        raise ReceiptValidationError("seal_duplicate_admitted_record")

    canonical_hashes = {
        hash_name: sha256_bytes(
            git_object_bytes(root, content_sha, relative_path)
        )
        for hash_name, relative_path in CANONICAL_PATHS.items()
    }
    receipt = {
        "schema_version": 2,
        "receipt_type": "batch",
        "batch_id": batch_id,
        "batch_mode": source.get("batch_mode"),
        "controller_run_id": source.get("controller_run_id"),
        "base_sha": source.get("base_sha"),
        "canonical_main_sha": source.get("canonical_main_sha"),
        "candidate_content_commit_sha": content_sha,
        "pr_number": source.get("pr_number"),
        "source_issue_number": source.get("source_issue_number"),
        "receipt_issue_number": source.get("receipt_issue_number"),
        "source_comment_watermark": FROZEN_WATERMARK,
        "full_queue_count": FROZEN_COUNT,
        "latest_observed_comment_id": FROZEN_WATERMARK,
        "latest_observed_update_time": max(
            item["updated_at"] for item in fingerprints if item.get("updated_at")
        ),
        "queue_snapshot_sha256": snapshot_hash,
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
    except jsonschema.ValidationError as error:
        raise ReceiptValidationError("seal_schema_failure") from error
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
