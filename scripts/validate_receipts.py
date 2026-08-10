#!/usr/bin/env python3
"""Validate every tracked batch receipt against immutable Git-object bytes."""

from __future__ import annotations

import argparse
import json
import os
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
from scripts.processor.batch_processor import (
    ProcessBatchConfig,
    build_batch_candidate,
    fetch_single_comment,
)
from scripts.processor.frozen_replay import replay_frozen_from_receipt
from scripts.processor.frozen_source import refetch_frozen_source
from scripts.processor.intake_parser import INTAKE_MARKER

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


def _running_on_canonical_main(root: Path, authority_sha: str) -> bool:
    if (
        os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REF_NAME") == "main"
    ):
        return True
    branch = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if branch.returncode != 0 or branch.stdout.strip() != "main":
        return False
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return head.returncode == 0 and head.stdout.strip() == authority_sha


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
    source_replay = value.get("source_replay")
    if value.get("batch_id") == FROZEN_BATCH_ID:
        if source_replay is not None:
            raise ReceiptValidationError("receipt_frozen_replay_contract_invalid")
    elif source_replay != {"adapter": "github-intake-v1"}:
        raise ReceiptValidationError("receipt_replay_contract_unsupported")
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


def validate_all_tracked_batch_receipts(
    root: Path,
    *,
    authority_sha: str,
    mode: str,
) -> dict[str, Any]:
    authority_sha = resolve_commit(root, authority_sha)
    if mode == "pr" and _running_on_canonical_main(root, authority_sha):
        mode = "canonical-main"
    schema = _load_schema(root)
    paths = tracked_batch_receipts(root, authority_sha)
    if not paths:
        raise ReceiptValidationError("receipt_missing")
    parsed: dict[str, dict[str, Any]] = {}
    batch_ids: set[str] = set()
    for path in paths:
        receipt = _parse_batch(git_object_bytes(root, authority_sha, path), schema)
        batch_id = receipt["batch_id"]
        expected_path = f"{RECEIPT_PREFIX}{batch_id}.json"
        if path != expected_path:
            raise ReceiptValidationError("receipt_path_identity_mismatch")
        if batch_id in batch_ids:
            raise ReceiptValidationError("receipt_duplicate_batch_id")
        batch_ids.add(batch_id)
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

    seals: dict[str, str] = {}
    for path, receipt in parsed.items():
        seal_sha = _terminal_seal_commit(
            root,
            authority_sha=authority_sha,
            mode=mode,
            receipt_path=path,
        )
        candidate_sha = resolve_commit(root, receipt["candidate_content_commit_sha"])
        _validate_terminal_seal_scope(
            root,
            seal_sha=seal_sha,
            receipt_path=path,
            candidate_sha=candidate_sha,
        )
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", seal_sha, authority_sha],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if ancestor.returncode != 0:
            raise ReceiptValidationError("receipt_seal_not_ancestor")
        if git_object_bytes(root, seal_sha, path) != git_object_bytes(
            root, authority_sha, path
        ):
            raise ReceiptValidationError("receipt_historical_bytes_changed")
        if path == changed_path and seal_sha != authority_sha:
            raise ReceiptValidationError("receipt_current_terminal_not_seal")
        seals[path] = seal_sha

    return {
        "mode": mode,
        "authority_sha": authority_sha,
        "receipt_count": len(paths),
        "receipt_paths": paths,
        "receipt_seals": seals,
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
    del mode
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


def _validate_frozen_source_replay(
    root: Path,
    *,
    receipt: Mapping[str, Any],
    candidate_sha: str,
    seal_sha: str,
) -> dict[str, int]:
    try:
        live = refetch_frozen_source(root, receipt)
        comments = live.get("comments")
        if not isinstance(comments, list):
            raise ProcessorError("processor_source_unavailable")
        replay = replay_frozen_from_receipt(root, receipt, comments)
    except (OSError, ValueError, ProcessorError) as error:
        raise ReceiptValidationError("receipt_source_replay_unavailable") from error

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
            raise ReceiptValidationError(f"receipt_source_replay_mismatch:{field}")
    for relative_path, expected in replay.candidate_files.items():
        if git_object_bytes(root, candidate_sha, relative_path) != expected:
            raise ReceiptValidationError("receipt_candidate_replay_mismatch")
        if git_object_bytes(root, seal_sha, relative_path) != expected:
            raise ReceiptValidationError("receipt_terminal_content_mismatch")
    return {
        "outcomes": len(replay.terminal_outcomes),
        "admissions": len(replay.admitted_run_ids),
        "later_comments": replay.later_comment_count,
    }


def _validate_github_intake_source_replay(
    root: Path,
    *,
    authority_sha: str,
    receipt_path: str,
    receipt: Mapping[str, Any],
    candidate_sha: str,
    seal_sha: str,
) -> dict[str, int]:
    try:
        comments = [
            fetch_single_comment(comment_id, root)
            for comment_id in receipt["source_comment_ids"]
        ]
        by_id = {int(item["id"]): item for item in comments}
        if len(by_id) != len(comments):
            raise ProcessorError("source_changed")
        owner: dict[str, Any] = {}
        owner_identity: Optional[tuple[int, str]] = None
        bindings = {item["comment_id"]: item for item in receipt["comment_bindings"]}
        for comment_id in receipt["source_comment_ids"]:
            comment = by_id.get(comment_id)
            binding = bindings.get(comment_id)
            if not isinstance(comment, dict) or not isinstance(binding, dict):
                raise ProcessorError("source_changed")
            body = comment.get("body")
            if (
                not isinstance(body, str)
                or sha256_bytes(body.encode("utf-8")) != binding.get("body_sha256")
                or comment.get("created_at") != binding.get("created_at")
                or comment.get("updated_at") != binding.get("updated_at")
            ):
                raise ProcessorError("source_changed")
            if body.startswith(INTAKE_MARKER):
                user = comment.get("user")
                identity = (
                    user.get("id") if isinstance(user, dict) else None,
                    user.get("login") if isinstance(user, dict) else None,
                )
                if (
                    comment.get("author_association") != "OWNER"
                    or not isinstance(identity[0], int)
                    or isinstance(identity[0], bool)
                    or identity[0] <= 0
                    or not isinstance(identity[1], str)
                    or not identity[1]
                    or (owner_identity is not None and identity != owner_identity)
                ):
                    raise ProcessorError("authority_missing")
                owner_identity = identity
                owner = {"id": identity[0], "login": identity[1]}

        config = ProcessBatchConfig(
            operating_mode=receipt["batch_mode"],
            base_sha=receipt["base_sha"],
            canonical_main_sha=receipt["canonical_main_sha"],
            batch_id=receipt["batch_id"],
            controller_run_id=receipt["controller_run_id"],
            pr_number=receipt["pr_number"],
            expected_head_sha=authority_sha,
            activation_mode="dry-run",
            dry_run=True,
            source_issue_number=receipt["source_issue_number"],
            receipt_issue_number=receipt["receipt_issue_number"],
            repository_root=root,
            candidate_content_commit_sha=candidate_sha,
        )
        candidate_files, evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=lambda _root: comments,
            comment_fetcher=lambda comment_id, _root: by_id[comment_id],
            canonical_main_fetcher=lambda _root: receipt["canonical_main_sha"],
            owner_fetcher=lambda _root: owner,
        )
    except (KeyError, OSError, TypeError, ValueError, ProcessorError) as error:
        raise ReceiptValidationError("receipt_source_replay_unavailable") from error

    replayed_receipt = candidate_files.get(receipt_path)
    if replayed_receipt != git_object_bytes(root, seal_sha, receipt_path):
        raise ReceiptValidationError("receipt_source_replay_mismatch:receipt")
    for relative_path in CANONICAL_PATHS.values():
        expected = candidate_files.get(relative_path)
        if expected is None or git_object_bytes(root, candidate_sha, relative_path) != expected:
            raise ReceiptValidationError("receipt_candidate_replay_mismatch")
    return {
        "outcomes": int(evidence["terminal_count"]),
        "admissions": int(evidence["admitted_count"]),
        "later_comments": 0,
    }


def validate_source_replay(
    root: Path,
    *,
    authority_sha: str,
    mode: str,
) -> dict[str, Any]:
    """Validate every receipt using its declared immutable source adapter."""

    structural = validate_all_tracked_batch_receipts(
        root,
        authority_sha=authority_sha,
        mode=mode,
    )
    authority_sha = structural["authority_sha"]
    schema = _load_schema(root)
    replayed_outcomes = 0
    replayed_admissions = 0
    later_comments = 0
    replayed_receipts: list[dict[str, str]] = []
    for receipt_path in structural["receipt_paths"]:
        receipt = _parse_batch(
            git_object_bytes(root, authority_sha, receipt_path),
            schema,
        )
        candidate_sha = resolve_commit(root, receipt["candidate_content_commit_sha"])
        seal_sha = structural["receipt_seals"][receipt_path]
        if receipt["batch_id"] == FROZEN_BATCH_ID:
            evidence = _validate_frozen_source_replay(
                root,
                receipt=receipt,
                candidate_sha=candidate_sha,
                seal_sha=seal_sha,
            )
            adapter = "frozen-v1"
        elif receipt.get("source_replay") == {"adapter": "github-intake-v1"}:
            evidence = _validate_github_intake_source_replay(
                root,
                authority_sha=authority_sha,
                receipt_path=receipt_path,
                receipt=receipt,
                candidate_sha=candidate_sha,
                seal_sha=seal_sha,
            )
            adapter = "github-intake-v1"
        else:
            raise ReceiptValidationError("receipt_replay_contract_unsupported")
        replayed_outcomes += evidence["outcomes"]
        replayed_admissions += evidence["admissions"]
        later_comments += evidence["later_comments"]
        replayed_receipts.append(
            {"path": receipt_path, "adapter": adapter, "seal_sha": seal_sha}
        )

    return {
        **structural,
        "validation_level": "source-replay",
        "replayed_receipts": replayed_receipts,
        "replayed_outcome_count": replayed_outcomes,
        "replayed_admission_count": replayed_admissions,
        "later_comment_count": later_comments,
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
