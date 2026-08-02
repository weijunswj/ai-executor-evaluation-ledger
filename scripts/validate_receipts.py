#!/usr/bin/env python3
"""Validate every tracked batch receipt against immutable Git-object bytes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.processor.common import (
    FROZEN_BATCH_ID,
    ProcessorError,
    sha256_bytes,
    validate_batch_receipt_closure,
    valid_git_sha,
)
from scripts.processor.frozen_replay import replay_frozen_from_receipt
from scripts.processor.frozen_source import refetch_frozen_source

RECEIPT_PREFIX = "ledger/receipts/batches/"
CANONICAL_PATHS = {
    "evaluations_jsonl": "evaluations.jsonl",
    "dispositions_jsonl": "ledger/dispositions.jsonl",
    "readme_md": "README.md",
    "scorecard_md": "scorecard.md",
    "model_recommendation_json": "analysis/model-recommendation.json",
}
FORBIDDEN_BATCH_KEYS = frozenset(
    {
        "author",
        "author_sha256",
        "reason",
        "pending_reason",
        "pending_reason_code",
        "validation_message",
        "schema_fragment",
        "exception",
        "log",
        "path",
        "url",
    }
)


class ReceiptValidationError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ReceiptValidationError("receipt_duplicate_json_key")
        value[key] = child
    return value


def _reject_nonfinite(_value: str) -> None:
    raise ReceiptValidationError("receipt_nonfinite_json_number")


def _canonical_document_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _git(root: Path, *args: str, text: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=text,
        check=False,
    )
    if result.returncode != 0:
        raise ReceiptValidationError("receipt_git_authority_unavailable")
    return result.stdout


def resolve_commit(root: Path, revision: str) -> str:
    value = str(_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}", text=True)).strip()
    if not valid_git_sha(value):
        raise ReceiptValidationError("receipt_git_authority_unavailable")
    return value


def git_object_bytes(root: Path, revision: str, relative_path: str) -> bytes:
    if relative_path.startswith(("/", "\\")) or ".." in Path(relative_path).parts:
        raise ReceiptValidationError("receipt_invalid_path")
    return bytes(_git(root, "show", f"{revision}:{relative_path}"))


def tracked_batch_receipts(root: Path, revision: str) -> list[str]:
    output = str(
        _git(
            root,
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            RECEIPT_PREFIX,
            text=True,
        )
    )
    paths = sorted(line for line in output.splitlines() if line.endswith(".json"))
    if len(paths) != len(set(paths)):
        raise ReceiptValidationError("receipt_duplicate_path")
    return paths


def _walk_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_BATCH_KEYS:
                raise ReceiptValidationError("receipt_forbidden_field")
            _walk_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden_keys(child)


def _load_schema(root: Path) -> dict[str, Any]:
    try:
        raw = (root / "schema" / "receipt.schema.json").read_bytes()
        if not raw or raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
            raise ReceiptValidationError("receipt_schema_bytes_invalid")
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
        if not isinstance(value, dict) or _canonical_document_bytes(value) != raw:
            raise ReceiptValidationError("receipt_schema_noncanonical")
        jsonschema.Draft202012Validator.check_schema(value)
    except (OSError, UnicodeDecodeError, ValueError, ReceiptValidationError, jsonschema.SchemaError):
        raise ReceiptValidationError("receipt_schema_unavailable")
    return value


def _parse_batch(raw: bytes, schema: Mapping[str, Any]) -> dict[str, Any]:
    if not raw or raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ReceiptValidationError("receipt_bytes_invalid")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, ReceiptValidationError):
        raise ReceiptValidationError("receipt_invalid_json")
    if not isinstance(value, dict) or value.get("schema_version") != 2 or _canonical_document_bytes(value) != raw:
        raise ReceiptValidationError("receipt_legacy_or_invalid")
    try:
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(value)
    except jsonschema.ValidationError:
        raise ReceiptValidationError("receipt_schema_failure")
    if value.get("receipt_type") != "batch" or not validate_batch_receipt_closure(value):
        raise ReceiptValidationError("receipt_closure_failure")
    _walk_forbidden_keys(value)
    return value


def _record_lines(evaluations_bytes: bytes) -> dict[str, tuple[bytes, dict[str, Any]]]:
    if evaluations_bytes and (
        evaluations_bytes.startswith(b"\xef\xbb\xbf")
        or b"\r" in evaluations_bytes
        or not evaluations_bytes.endswith(b"\n")
        or evaluations_bytes.endswith(b"\n\n")
    ):
        raise ReceiptValidationError("receipt_unterminated_record")
    records: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for line in evaluations_bytes.splitlines(keepends=True):
        if not line.endswith(b"\n") or not line[:-1].strip():
            raise ReceiptValidationError("receipt_noncanonical_record_delimiter")
        try:
            value = json.loads(
                line[:-1].decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        except (UnicodeDecodeError, ValueError, ReceiptValidationError):
            raise ReceiptValidationError("receipt_invalid_record")
        run_id = value.get("run_id") if isinstance(value, dict) else None
        if not isinstance(run_id, str) or run_id in records:
            raise ReceiptValidationError("receipt_duplicate_or_missing_record")
        records[run_id] = (line, value)
    return records


def _validate_content_at_commit(
    root: Path,
    commit_sha: str,
    receipt: Mapping[str, Any],
) -> None:
    for hash_name, relative_path in CANONICAL_PATHS.items():
        actual = sha256_bytes(git_object_bytes(root, commit_sha, relative_path))
        if receipt["canonical_hashes"].get(hash_name) != actual:
            raise ReceiptValidationError(f"receipt_aggregate_hash_mismatch:{hash_name}")
    records = _record_lines(git_object_bytes(root, commit_sha, CANONICAL_PATHS["evaluations_jsonl"]))
    expected_ids = set(receipt["canonical_record_hashes"])
    for run_id in expected_ids:
        if run_id not in records:
            raise ReceiptValidationError("receipt_record_missing")
        line, value = records[run_id]
        if sha256_bytes(line) != receipt["canonical_record_hashes"][run_id]:
            raise ReceiptValidationError(f"receipt_record_hash_mismatch:{run_id}")
        expected_proof = {
            "provider": value.get("provider"),
            "model": value.get("model"),
            "outcome": value.get("outcome"),
            "weighted_score_5": value.get("weighted_score_5"),
        }
        if receipt["accepted_record_proofs"].get(run_id) != expected_proof:
            raise ReceiptValidationError(f"receipt_record_proof_mismatch:{run_id}")


def validate_batch_receipt_object(
    root: Path,
    receipt: Mapping[str, Any],
    *,
    authority_sha: str,
) -> None:
    candidate_sha = receipt.get("candidate_content_commit_sha")
    if not valid_git_sha(candidate_sha):
        raise ReceiptValidationError("receipt_candidate_commit_invalid")
    candidate_sha = resolve_commit(root, candidate_sha)
    _validate_content_at_commit(root, candidate_sha, receipt)
    _validate_content_at_commit(root, authority_sha, receipt)


def validate_all_tracked_batch_receipts(
    root: Path,
    *,
    authority_sha: str,
    mode: str,
) -> dict[str, Any]:
    authority_sha = resolve_commit(root, authority_sha)
    schema = _load_schema(root)
    paths = tracked_batch_receipts(root, authority_sha)
    if not paths:
        raise ReceiptValidationError("receipt_missing")
    parsed: dict[str, dict[str, Any]] = {}
    for path in paths:
        receipt = _parse_batch(git_object_bytes(root, authority_sha, path), schema)
        validate_batch_receipt_object(root, receipt, authority_sha=authority_sha)
        parsed[path] = receipt

    changed_path: Optional[str] = None
    parent_sha: Optional[str] = None
    if mode == "pr":
        parent_line = str(
            _git(root, "rev-list", "--parents", "-n", "1", authority_sha, text=True)
        ).strip().split()
        if len(parent_line) != 2:
            raise ReceiptValidationError("receipt_final_head_parent_count")
        parent_sha = parent_line[1]
        changed = str(
            _git(
                root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                parent_sha,
                authority_sha,
                text=True,
            )
        ).splitlines()
        if len(changed) != 1 or changed[0] not in parsed:
            raise ReceiptValidationError("receipt_final_commit_scope")
        changed_path = changed[0]
        if parsed[changed_path]["candidate_content_commit_sha"] != parent_sha:
            raise ReceiptValidationError("receipt_candidate_parent_mismatch")
    elif mode != "canonical-main":
        raise ReceiptValidationError("receipt_invalid_mode")

    return {
        "mode": mode,
        "authority_sha": authority_sha,
        "receipt_count": len(paths),
        "receipt_paths": paths,
        "final_parent_sha": parent_sha,
        "changed_receipt_path": changed_path,
    }


def _terminal_seal_commit(
    root: Path,
    *,
    authority_sha: str,
    mode: str,
    receipt_path: str,
) -> str:
    if mode == "pr":
        return authority_sha
    value = str(
        _git(
            root,
            "log",
            "-1",
            "--format=%H",
            authority_sha,
            "--",
            receipt_path,
            text=True,
        )
    ).strip()
    if not valid_git_sha(value):
        raise ReceiptValidationError("receipt_terminal_seal_unavailable")
    return value


def _validate_terminal_seal_scope(
    root: Path,
    *,
    seal_sha: str,
    receipt_path: str,
    candidate_sha: str,
) -> None:
    parent_line = str(
        _git(root, "rev-list", "--parents", "-n", "1", seal_sha, text=True)
    ).strip().split()
    if len(parent_line) != 2 or parent_line[1] != candidate_sha:
        raise ReceiptValidationError("receipt_candidate_parent_mismatch")
    changed = str(
        _git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            candidate_sha,
            seal_sha,
            text=True,
        )
    ).splitlines()
    if changed != [receipt_path]:
        raise ReceiptValidationError("receipt_final_commit_scope")


def validate_source_replay(
    root: Path,
    *,
    authority_sha: str,
    mode: str,
) -> dict[str, Any]:
    """Validate source semantics independently of prior receipt outcomes."""

    structural = validate_all_tracked_batch_receipts(
        root,
        authority_sha=authority_sha,
        mode=mode,
    )
    authority_sha = structural["authority_sha"]
    paths = structural["receipt_paths"]
    if len(paths) != 1:
        raise ReceiptValidationError("receipt_terminal_receipt_count")
    receipt_path = paths[0]
    schema = _load_schema(root)
    receipt = _parse_batch(
        git_object_bytes(root, authority_sha, receipt_path),
        schema,
    )
    if receipt.get("batch_id") != FROZEN_BATCH_ID:
        raise ReceiptValidationError("receipt_frozen_batch_mismatch")
    candidate_sha = resolve_commit(
        root,
        receipt["candidate_content_commit_sha"],
    )
    seal_sha = _terminal_seal_commit(
        root,
        authority_sha=authority_sha,
        mode=mode,
        receipt_path=receipt_path,
    )
    _validate_terminal_seal_scope(
        root,
        seal_sha=seal_sha,
        receipt_path=receipt_path,
        candidate_sha=candidate_sha,
    )
    if git_object_bytes(root, seal_sha, receipt_path) != git_object_bytes(
        root,
        authority_sha,
        receipt_path,
    ):
        raise ReceiptValidationError("receipt_terminal_receipt_not_current")

    try:
        live = refetch_frozen_source(root, receipt)
        comments = live.get("comments")
        if not isinstance(comments, list):
            raise ProcessorError("processor_source_unavailable")
        replay = replay_frozen_from_receipt(root, receipt, comments)
    except (OSError, ValueError, ProcessorError) as error:
        raise ReceiptValidationError(
            "receipt_source_replay_unavailable"
        ) from error

    comparisons = {
        "terminal_outcomes": dict(replay.terminal_outcomes),
        "admitted_run_ids": list(replay.admitted_run_ids),
        "accepted_record_proofs": dict(replay.accepted_record_proofs),
        "canonical_record_hashes": dict(replay.canonical_record_hashes),
        "canonical_hashes": dict(replay.canonical_hashes),
        "comment_bindings": list(replay.comment_bindings),
        "source_comment_ids": list(replay.source_comment_ids),
        "source_body_sha256": dict(replay.source_body_sha256),
        "queue_snapshot_sha256": replay.source_snapshot_sha256,
    }
    for field, expected in comparisons.items():
        if receipt.get(field) != expected:
            raise ReceiptValidationError(
                f"receipt_source_replay_mismatch:{field}"
            )
    for relative_path, expected in replay.candidate_files.items():
        if git_object_bytes(root, candidate_sha, relative_path) != expected:
            raise ReceiptValidationError(
                "receipt_candidate_replay_mismatch"
            )
        if git_object_bytes(root, seal_sha, relative_path) != expected:
            raise ReceiptValidationError(
                "receipt_terminal_content_mismatch"
            )

    return {
        **structural,
        "validation_level": "source-replay",
        "seal_sha": seal_sha,
        "candidate_sha": candidate_sha,
        "replayed_outcome_count": len(replay.terminal_outcomes),
        "replayed_admission_count": len(replay.admitted_run_ids),
        "later_comment_count": replay.later_comment_count,
    }


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="validate_receipts")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--mode", choices=["pr", "canonical-main"], default="pr")
    parser.add_argument("--authority-sha", default="HEAD")
    parser.add_argument(
        "--validation-level",
        choices=["structural", "source-replay"],
        default="structural",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        if args.validation_level == "source-replay":
            evidence = validate_source_replay(
                args.repository_root,
                authority_sha=args.authority_sha,
                mode=args.mode,
            )
        else:
            evidence = validate_all_tracked_batch_receipts(
                args.repository_root,
                authority_sha=args.authority_sha,
                mode=args.mode,
            )
    except ReceiptValidationError:
        print("Batch receipt validation failed.", file=sys.stderr)
        return 1
    if args.validation_level == "source-replay":
        print(
            "Batch receipt source replay passed: "
            f"{evidence['replayed_outcome_count']} outcomes and "
            f"{evidence['replayed_admission_count']} admissions at "
            f"{evidence['authority_sha']}."
        )
    else:
        print(
            "Batch receipt structural validation passed: "
            f"{evidence['receipt_count']} tracked receipt(s) at "
            f"{evidence['authority_sha']}; semantic source replay not run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
