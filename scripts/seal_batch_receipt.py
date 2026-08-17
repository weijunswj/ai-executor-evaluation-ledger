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

from scripts.processor.common import (
    git_tree_file_bindings,
    git_tree_manifest_sha256,
    sha256_bytes,
    validate_batch_receipt_closure,
)
from scripts.processor.frozen_source import (
    FROZEN_BATCH_ID,
    FROZEN_COUNT,
    FROZEN_WATERMARK,
    refetch_frozen_source,
)
from scripts.processor.frozen_replay import replay_frozen_from_receipt
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    git_object_bytes,
    resolve_commit,
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


FROZEN_GENERATED_VIEW_PATHS = frozenset(
    {
        "README.md",
        "scorecard.md",
        "analysis/model-recommendation.json",
    }
)


FROZEN_APPEND_ONLY_PATHS = frozenset(
    {
        "evaluations.jsonl",
        "ledger/dispositions.jsonl",
    }
)


def _verify_frozen_replay_artifacts(
    root: Path,
    content_sha: str,
    replay: Any,
) -> None:
    for relative_path, expected in replay.candidate_files.items():
        actual = git_object_bytes(root, content_sha, relative_path)
        if relative_path in FROZEN_APPEND_ONLY_PATHS:
            if not actual.startswith(expected):
                raise ReceiptValidationError("seal_candidate_replay_mismatch")
        elif relative_path in FROZEN_GENERATED_VIEW_PATHS:
            continue
        elif actual != expected:
            raise ReceiptValidationError("seal_candidate_replay_mismatch")


def _full_current_canonical_hashes(root: Path, content_sha: str) -> dict[str, str]:
    return {
        hash_name: sha256_bytes(git_object_bytes(root, content_sha, relative_path))
        for hash_name, relative_path in CANONICAL_PATHS.items()
    }


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
    comments = live.get("comments")
    if (
        not isinstance(fingerprints, list)
        or len(fingerprints) != FROZEN_COUNT
        or not isinstance(comments, list)
        or len(comments) != FROZEN_COUNT
    ):
        raise ReceiptValidationError("seal_frozen_source_invalid")
    try:
        replay = replay_frozen_from_receipt(root, source, comments)
    except Exception as error:
        raise ReceiptValidationError("seal_replay_failure") from error
    _verify_frozen_replay_artifacts(root, content_sha, replay)
    source_ids = list(replay.source_comment_ids)
    receipt_path = f"ledger/receipts/batches/{batch_id}.json"
    candidate_manifest = git_tree_file_bindings(
        root,
        content_sha,
        excluded_paths=(receipt_path,),
    )
    receipt = {
        "schema_version": 2,
        "receipt_type": "batch",
        "batch_id": batch_id,
        "batch_mode": source.get("batch_mode"),
        "controller_run_id": source.get("controller_run_id"),
        "base_sha": source.get("base_sha"),
        "canonical_main_sha": source.get("canonical_main_sha"),
        "candidate_content_commit_sha": content_sha,
        "candidate_content_manifest": candidate_manifest,
        "candidate_content_manifest_sha256": git_tree_manifest_sha256(
            candidate_manifest
        ),
        "pr_number": source.get("pr_number"),
        "source_issue_number": source.get("source_issue_number"),
        "receipt_issue_number": source.get("receipt_issue_number"),
        "source_comment_watermark": FROZEN_WATERMARK,
        "full_queue_count": FROZEN_COUNT,
        "latest_observed_comment_id": FROZEN_WATERMARK,
        "latest_observed_update_time": max(
            item["updated_at"]
            for item in replay.comment_bindings
            if item.get("updated_at")
        ),
        "queue_snapshot_sha256": replay.source_snapshot_sha256,
        "source_comment_ids": source_ids,
        "source_body_sha256": dict(replay.source_body_sha256),
        "selected_comment_ids": source_ids,
        "selected_comment_count": FROZEN_COUNT,
        "terminal_outcome_count": FROZEN_COUNT,
        "terminal_outcomes": dict(replay.terminal_outcomes),
        "admitted_run_ids": list(replay.admitted_run_ids),
        "accepted_record_proofs": dict(replay.accepted_record_proofs),
        "canonical_record_hashes": dict(replay.canonical_record_hashes),
        "canonical_hashes": _full_current_canonical_hashes(root, content_sha),
        "comment_bindings": list(replay.comment_bindings),
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
