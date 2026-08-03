"""Candidate-first integrated Ledger batch processor."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import jsonschema

from scripts.check_public_safety import audit_tree
from scripts.processor.common import (
    AUTHORIZED_PAIRS,
    FROZEN_BATCH_ID,
    ProcessorError,
    canonical_json_bytes,
    canonical_json_line_bytes,
    reject_duplicate_json_keys,
    safe_author_hash,
    safe_comment_body_hash,
    sha256_bytes,
    validate_batch_receipt_closure,
    valid_author_login,
    valid_git_sha,
    valid_identifier,
)
from scripts.processor.frozen_replay import (
    FrozenBatchPolicy,
    replay_frozen_from_receipt,
)
from scripts.processor.intake_parser import (
    canonical_record_from_payload,
    parse_intake_comment,
)
from scripts.processor.github_cli import gh_json
from scripts.processor.transaction import (
    build_complete_candidate_tree,
    recover_incomplete_transaction,
    replace_tracked_files,
)
from scripts.rebuild_views import expected_files_for_records, resolved_evaluations

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "evaluations.jsonl"
DISPOSITIONS_PATH = ROOT / "ledger" / "dispositions.jsonl"
BATCH_RECEIPTS_DIR = ROOT / "ledger" / "receipts" / "batches"
EVALUATION_SCHEMA_PATH = ROOT / "schema" / "evaluation.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
DISPOSITION_SCHEMA_PATH = ROOT / "schema" / "disposition.schema.json"

EVALUATION_SCHEMA = json.loads(EVALUATION_SCHEMA_PATH.read_text(encoding="utf-8"))
RECEIPT_SCHEMA = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
DISPOSITION_SCHEMA = json.loads(DISPOSITION_SCHEMA_PATH.read_text(encoding="utf-8"))
FORMAT_CHECKER = jsonschema.FormatChecker()
EVALUATION_VALIDATOR = jsonschema.Draft202012Validator(EVALUATION_SCHEMA, format_checker=FORMAT_CHECKER)
RECEIPT_VALIDATOR = jsonschema.Draft202012Validator(RECEIPT_SCHEMA, format_checker=FORMAT_CHECKER)
DISPOSITION_VALIDATOR = jsonschema.Draft202012Validator(DISPOSITION_SCHEMA, format_checker=FORMAT_CHECKER)


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


@dataclass(frozen=True)
class ProcessBatchConfig:
    operating_mode: str
    base_sha: str
    canonical_main_sha: str
    batch_id: str
    controller_run_id: str
    pr_number: int
    expected_head_sha: str
    activation_mode: str
    dry_run: bool
    source_issue_number: int
    receipt_issue_number: int
    repository_root: Path
    operator_intent: Optional[str] = None
    reviewed_pr_state: Optional[str] = None
    merge_state: Optional[str] = None
    checks_state: Optional[str] = None
    review_state: Optional[str] = None
    candidate_content_commit_sha: Optional[str] = None


def compute_sha256(content: bytes) -> str:
    return sha256_bytes(content)


def _run_git(repository_root: Path, args: List[str], *, text: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        text=text,
        check=False,
    )
    if result.returncode != 0:
        raise ProcessorError("authority_missing")
    return result


def read_git_object(repository_root: Path, revision: str, relative_path: str) -> bytes:
    if not valid_git_sha(revision):
        raise ProcessorError("authority_missing")
    result = _run_git(repository_root, ["show", f"{revision}:{relative_path}"])
    return result.stdout


def list_git_paths(repository_root: Path, revision: str, prefix: str) -> List[str]:
    result = _run_git(repository_root, ["ls-tree", "-r", "--name-only", revision, "--", prefix], text=True)
    return [line for line in result.stdout.splitlines() if line.endswith(".json")]


def _validate_json_lines(content: bytes) -> List[Dict[str, Any]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ProcessorError("authority_missing")
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=reject_duplicate_json_keys,
                parse_constant=_reject_nonfinite_constant,
            )
        except (TypeError, ValueError):
            raise ProcessorError("processor_schema_failure")
        if not isinstance(value, dict):
            raise ProcessorError("processor_schema_failure")
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or run_id in seen:
            raise ProcessorError("processor_schema_failure")
        if not any(EVALUATION_VALIDATOR.iter_errors(value)):
            records.append(value)
            seen.add(run_id)
        else:
            raise ProcessorError("processor_schema_failure")
    return records


def load_canonical_base_records(repository_root: Path, base_sha: str) -> List[Dict[str, Any]]:
    return _validate_json_lines(read_git_object(repository_root, base_sha, "evaluations.jsonl"))


def load_canonical_main_records(repository_root: Path, canonical_main_sha: str) -> List[Dict[str, Any]]:
    """Always read incremental authority through an immutable Git object."""

    return _validate_json_lines(read_git_object(repository_root, canonical_main_sha, "evaluations.jsonl"))


def _ensure_newline(content: bytes) -> bytes:
    return content if not content or content.endswith(b"\n") else content + b"\n"


def _safe_gh_json(repository_root: Path, args: List[str], *, paginate: bool = False) -> Any:
    return gh_json(
        repository_root,
        args,
        failure_code="processor_source_unavailable",
        paginate=paginate,
    )


def fetch_live_142_comments(repository_root: Path = ROOT) -> List[Dict[str, Any]]:
    pages = _safe_gh_json(
        repository_root,
        ["repos/weijunswj/ai-executor-evaluation-ledger/issues/142/comments"],
        paginate=True,
    )
    if not isinstance(pages, list):
        raise ProcessorError("processor_source_unavailable")
    comments: List[Dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise ProcessorError("processor_source_unavailable")
        comments.extend(item for item in page if isinstance(item, dict))
    return comments


def fetch_single_comment(comment_id: int, repository_root: Path = ROOT) -> Dict[str, Any]:
    value = _safe_gh_json(
        repository_root,
        [f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"],
    )
    if not isinstance(value, dict):
        raise ProcessorError("processor_source_unavailable")
    return value


def fetch_issue_metadata(repository_root: Path = ROOT) -> Dict[str, Any]:
    value = _safe_gh_json(
        repository_root,
        ["repos/weijunswj/ai-executor-evaluation-ledger/issues/142"],
    )
    if not isinstance(value, dict):
        raise ProcessorError("processor_source_unavailable")
    return value


def fetch_live_canonical_main_sha(repository_root: Path = ROOT) -> str:
    value = _safe_gh_json(
        repository_root,
        ["repos/weijunswj/ai-executor-evaluation-ledger/git/ref/heads/main"],
    )
    sha = value.get("object", {}).get("sha") if isinstance(value, dict) else None
    if not valid_git_sha(sha):
        raise ProcessorError("processor_authority_mismatch")
    return sha


def _comment_fingerprint(comment: Mapping[str, Any]) -> Dict[str, Any]:
    comment_id = comment.get("id")
    body = comment.get("body")
    user = comment.get("user")
    author = user.get("login") if isinstance(user, dict) else None
    created_at = comment.get("created_at")
    updated_at = comment.get("updated_at")
    if (
        not isinstance(comment_id, int)
        or comment_id <= 0
        or not isinstance(body, str)
        or not valid_author_login(author)
    ):
        raise ProcessorError("source_changed")
    if created_at is not None and not isinstance(created_at, str):
        raise ProcessorError("source_changed")
    if updated_at is not None and not isinstance(updated_at, str):
        raise ProcessorError("source_changed")
    return {
        "id": comment_id,
        "author_sha256": safe_author_hash(author),
        "created_at": created_at,
        "updated_at": updated_at,
        "body_sha256": safe_comment_body_hash(body),
    }


def _queue_snapshot(comments: Iterable[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    fingerprints = [_comment_fingerprint(comment) for comment in comments]
    fingerprints.sort(key=lambda item: item["id"])
    ids = [item["id"] for item in fingerprints]
    if len(ids) != len(set(ids)):
        raise ProcessorError("source_changed")
    return fingerprints, sha256_bytes(canonical_json_bytes(fingerprints))


def _same_snapshot(left: List[Mapping[str, Any]], right: List[Mapping[str, Any]]) -> bool:
    try:
        return _queue_snapshot(left)[0] == _queue_snapshot(right)[0]
    except ProcessorError:
        return False


def _verify_selected_comment(ref: Mapping[str, Any], fresh: Mapping[str, Any]) -> None:
    if _comment_fingerprint(ref) != _comment_fingerprint(fresh):
        raise ProcessorError("source_changed")


def _validate_config(config: ProcessBatchConfig) -> None:
    if config.operating_mode not in {"initial", "incremental"}:
        raise ProcessorError("processor_invalid_contract")
    if not valid_git_sha(config.base_sha) or not valid_git_sha(config.canonical_main_sha):
        raise ProcessorError("processor_invalid_contract")
    if not valid_git_sha(config.expected_head_sha):
        raise ProcessorError("processor_invalid_contract")
    if (
        config.candidate_content_commit_sha is not None
        and not valid_git_sha(config.candidate_content_commit_sha)
    ):
        raise ProcessorError("processor_invalid_contract")
    if not valid_identifier(config.batch_id) or not valid_identifier(config.controller_run_id):
        raise ProcessorError("processor_invalid_contract")
    if not isinstance(config.pr_number, int) or config.pr_number <= 0:
        raise ProcessorError("processor_invalid_contract")
    if config.source_issue_number != 142 or config.receipt_issue_number != 143:
        raise ProcessorError("processor_invalid_contract")
    if config.activation_mode not in {"dry-run", "reviewed-live"}:
        raise ProcessorError("processor_invalid_contract")
    if config.dry_run != (config.activation_mode == "dry-run"):
        raise ProcessorError("processor_invalid_contract")
    if not config.repository_root.exists():
        raise ProcessorError("processor_invalid_contract")
    if config.base_sha != config.canonical_main_sha:
        raise ProcessorError("processor_invalid_contract")
    if config.activation_mode == "reviewed-live":
        if config.operator_intent != "reviewed":
            raise ProcessorError("processor_activation_denied")
        if config.reviewed_pr_state != "merged" or config.merge_state != "merged":
            raise ProcessorError("processor_activation_denied")
        if config.checks_state != "passed" or config.review_state != "clear":
            raise ProcessorError("processor_activation_denied")
    _run_git(config.repository_root, ["cat-file", "-e", f"{config.base_sha}^{{commit}}"])
    _run_git(config.repository_root, ["cat-file", "-e", f"{config.canonical_main_sha}^{{commit}}"])
    _run_git(config.repository_root, ["cat-file", "-e", f"{config.expected_head_sha}^{{commit}}"])
    if config.candidate_content_commit_sha is not None:
        _run_git(
            config.repository_root,
            ["cat-file", "-e", f"{config.candidate_content_commit_sha}^{{commit}}"],
        )
    head_result = _run_git(config.repository_root, ["rev-parse", "HEAD"], text=True)
    if head_result.stdout.strip() != config.expected_head_sha:
        raise ProcessorError("processor_authority_mismatch")
    read_git_object(config.repository_root, config.base_sha, "evaluations.jsonl")
    read_git_object(config.repository_root, config.canonical_main_sha, "evaluations.jsonl")


def _authority_files(config: ProcessBatchConfig) -> Tuple[Dict[str, bytes], List[Dict[str, Any]]]:
    authority_sha = config.base_sha if config.operating_mode == "initial" else config.canonical_main_sha
    view_sha = authority_sha if config.operating_mode == "initial" else config.canonical_main_sha
    evaluation_bytes = read_git_object(config.repository_root, authority_sha, "evaluations.jsonl")
    records = _validate_json_lines(evaluation_bytes)
    files = {
        "evaluations.jsonl": evaluation_bytes,
        "ledger/dispositions.jsonl": read_git_object(config.repository_root, authority_sha, "ledger/dispositions.jsonl"),
        "README.md": read_git_object(config.repository_root, view_sha, "README.md"),
        "scorecard.md": read_git_object(config.repository_root, view_sha, "scorecard.md"),
        "analysis/model-recommendation.json": read_git_object(
            config.repository_root,
            view_sha,
            "analysis/model-recommendation.json",
        ),
    }
    for path in list_git_paths(config.repository_root, authority_sha, "ledger/receipts/batches"):
        files[path] = read_git_object(config.repository_root, authority_sha, path)
    return files, records


def _append_jsonl(existing: bytes, lines: Iterable[bytes]) -> bytes:
    output = _ensure_newline(existing)
    for line in lines:
        output += line
    return output


def _validate_candidate_tree(
    candidate_path: Path,
    candidate_files: Mapping[str, bytes],
    records: List[Dict[str, Any]],
    dispositions: List[Dict[str, Any]],
    batch_receipt: Optional[Dict[str, Any]],
    rejected_sentinels: Iterable[bytes] = (),
) -> None:
    for error in EVALUATION_VALIDATOR.iter_errors(records[0]) if records else ():
        raise ProcessorError("processor_schema_failure")
    for record in records:
        if any(EVALUATION_VALIDATOR.iter_errors(record)):
            raise ProcessorError("processor_schema_failure")
    for disposition in dispositions:
        if any(DISPOSITION_VALIDATOR.iter_errors(disposition)):
            raise ProcessorError("processor_schema_failure")
    if batch_receipt is not None:
        if any(RECEIPT_VALIDATOR.iter_errors(batch_receipt)):
            raise ProcessorError("processor_schema_failure")
        if not validate_batch_receipt_closure(batch_receipt):
            raise ProcessorError("processor_schema_failure")
    for relative_path, expected in candidate_files.items():
        actual = (candidate_path / relative_path).read_bytes()
        if actual != expected:
            raise ProcessorError("processor_integrity_failure")
    for sentinel in rejected_sentinels:
        if any(sentinel in content for content in candidate_files.values()):
            raise ProcessorError("unsafe_content")
    try:
        readme = (candidate_path / "README.md").read_text(encoding="utf-8")
        scorecard = (candidate_path / "scorecard.md").read_text(encoding="utf-8")
        expected_readme, expected_scorecard, _ = expected_files_for_records(
            resolved_evaluations(records),
            readme,
            scorecard,
            queued_evaluations=[],
        )
    except Exception:
        raise ProcessorError("processor_integrity_failure")
    if readme != expected_readme or scorecard != expected_scorecard:
        raise ProcessorError("processor_integrity_failure")
    if audit_tree(candidate_path) != 0:
        raise ProcessorError("processor_public_safety_failure")


def _frozen_policy_receipt(config: ProcessBatchConfig) -> Dict[str, Any]:
    try:
        raw = read_git_object(
            config.repository_root,
            config.expected_head_sha,
            f"ledger/receipts/batches/{FROZEN_BATCH_ID}.json",
        )
        receipt = json.loads(
            raw.decode("utf-8", errors="strict"),
            parse_constant=_reject_nonfinite_constant,
        )
    except (UnicodeDecodeError, TypeError, ValueError):
        raise ProcessorError("source_changed")
    if not isinstance(receipt, dict):
        raise ProcessorError("source_changed")
    FrozenBatchPolicy.from_receipt(receipt)
    return receipt


def _build_frozen_candidate(
    config: ProcessBatchConfig,
    comments: Optional[List[Dict[str, Any]]],
    *,
    failure_hook: Optional[Callable[[str, str], None]],
    queue_fetcher: Callable[[Path], List[Dict[str, Any]]],
) -> Tuple[Dict[str, bytes], Dict[str, Any]]:
    policy_receipt = _frozen_policy_receipt(config)
    first_comments = (
        comments
        if comments is not None
        else queue_fetcher(config.repository_root)
    )
    replay = replay_frozen_from_receipt(
        config.repository_root,
        policy_receipt,
        first_comments,
    )
    policy = FrozenBatchPolicy.from_receipt(policy_receipt)
    final_source = policy.verify_source(queue_fetcher(config.repository_root))
    if final_source.snapshot_sha256 != replay.source_snapshot_sha256:
        raise ProcessorError("source_changed")

    candidate_files = dict(replay.candidate_files)
    if config.candidate_content_commit_sha is not None:
        for relative_path, expected in candidate_files.items():
            if read_git_object(
                config.repository_root,
                config.candidate_content_commit_sha,
                relative_path,
            ) != expected:
                raise ProcessorError("processor_integrity_failure")

    final_records = _validate_json_lines(candidate_files["evaluations.jsonl"])
    try:
        final_dispositions = [
            json.loads(line, parse_constant=_reject_nonfinite_constant)
            for line in candidate_files[
                "ledger/dispositions.jsonl"
            ].decode("utf-8", errors="strict").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, TypeError, ValueError):
        raise ProcessorError("processor_schema_failure")
    with build_complete_candidate_tree(
        config.repository_root,
        candidate_files,
    ) as candidate_tree:
        _validate_candidate_tree(
            candidate_tree.path,
            candidate_files,
            final_records,
            final_dispositions,
            None,
        )
        if failure_hook:
            failure_hook("candidate_validation_complete", "")

    return candidate_files, {
        "status": "CANDIDATE_VALIDATED",
        "batch_id": config.batch_id,
        "full_queue_count": len(replay.source_comment_ids),
        "selected_comment_count": len(replay.source_comment_ids),
        "admitted_count": len(replay.admitted_run_ids),
        "terminal_count": len(replay.terminal_outcomes),
        "snapshot_hash": replay.source_snapshot_sha256,
        "later_comment_count": replay.later_comment_count,
        "evaluations_sha256": replay.canonical_hashes[
            "evaluations_jsonl"
        ],
        "record_hashes": dict(replay.canonical_record_hashes),
        "receipt_sha256": None,
        "receipt_sealed": False,
        "candidate_files": tuple(sorted(candidate_files)),
    }


def build_batch_candidate(
    config: ProcessBatchConfig,
    comments: Optional[List[Dict[str, Any]]] = None,
    *,
    failure_hook: Optional[Callable[[str, str], None]] = None,
    queue_fetcher: Optional[Callable[[Path], List[Dict[str, Any]]]] = None,
    comment_fetcher: Optional[Callable[[int, Path], Dict[str, Any]]] = None,
    canonical_main_fetcher: Optional[Callable[[Path], str]] = None,
) -> Tuple[Dict[str, bytes], Dict[str, Any]]:
    _validate_config(config)
    canonical_main_fetcher = canonical_main_fetcher or fetch_live_canonical_main_sha
    if canonical_main_fetcher(config.repository_root) != config.canonical_main_sha:
        raise ProcessorError("processor_authority_mismatch")
    recover_incomplete_transaction(config.repository_root, failure_hook=failure_hook)
    queue_fetcher = queue_fetcher or fetch_live_142_comments
    if config.batch_id == FROZEN_BATCH_ID:
        return _build_frozen_candidate(
            config,
            comments,
            failure_hook=failure_hook,
            queue_fetcher=queue_fetcher,
        )
    authority_files, preserved_records = _authority_files(config)
    comment_fetcher = comment_fetcher or fetch_single_comment
    existing_receipt_path = f"ledger/receipts/batches/{config.batch_id}.json"
    if existing_receipt_path in authority_files:
        raise ProcessorError("receipt_conflict")
    if comments is None:
        comments = queue_fetcher(config.repository_root)
    comments = sorted(comments, key=lambda item: item.get("id", 0))
    first_fingerprints, first_queue_hash = _queue_snapshot(comments)

    for comment in comments:
        fresh = comment_fetcher(int(comment["id"]), config.repository_root)
        _verify_selected_comment(comment, fresh)

    recorded_run_ids = {record.get("run_id") for record in preserved_records}
    existing_disposition_bindings: set[tuple[int, str]] = set()
    for line in authority_files["ledger/dispositions.jsonl"].decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            disposition_value = json.loads(line, parse_constant=_reject_nonfinite_constant)
        except ValueError:
            raise ProcessorError("processor_schema_failure")
        if isinstance(disposition_value, dict):
            existing_id = disposition_value.get("comment_id")
            existing_hash = disposition_value.get("comment_body_sha256") or disposition_value.get("body_sha256")
            if isinstance(existing_id, int) and isinstance(existing_hash, str):
                existing_disposition_bindings.add((existing_id, existing_hash))
    seen_candidate_ids: set[str] = set()
    admitted_records: List[Dict[str, Any]] = []
    new_record_lines: List[bytes] = []
    new_record_hashes: Dict[str, str] = {}
    admitted_record_proofs: Dict[str, Dict[str, Any]] = {}
    disposition_lines: List[bytes] = []
    terminal_outcomes: Dict[str, Dict[str, Any]] = {}
    bindings: List[Dict[str, Any]] = []
    admitted_run_ids: List[str] = []

    for comment, fingerprint in zip(comments, first_fingerprints):
        comment_id = int(comment["id"])
        body = comment.get("body", "")
        code, payload, _ = parse_intake_comment(comment_id, body, recorded_run_ids, seen_candidate_ids)
        evaluation_run_id = None
        record_hash = None
        if code == "admitted":
            try:
                record = canonical_record_from_payload(payload)
            except (KeyError, TypeError):
                raise ProcessorError("authority_missing")
            if any(EVALUATION_VALIDATOR.iter_errors(record)):
                raise ProcessorError("processor_schema_failure")
            line_bytes = canonical_json_line_bytes(record)
            evaluation_run_id = record["run_id"]
            record_hash = sha256_bytes(line_bytes)
            admitted_records.append(record)
            new_record_lines.append(line_bytes)
            new_record_hashes[evaluation_run_id] = record_hash
            admitted_record_proofs[evaluation_run_id] = {
                "provider": record["provider"],
                "model": record["model"],
                "outcome": record["outcome"],
                "weighted_score_5": record["weighted_score_5"],
            }
            admitted_run_ids.append(evaluation_run_id)
            recorded_run_ids.add(evaluation_run_id)
        else:
            disposition = {
                "schema_version": 2,
                "comment_id": comment_id,
                "comment_body_sha256": fingerprint["body_sha256"],
                "disposition_code": code,
                "processed_at": fingerprint["updated_at"] or fingerprint["created_at"],
                "evaluation_run_id": None,
            }
            if any(DISPOSITION_VALIDATOR.iter_errors(disposition)):
                raise ProcessorError("processor_schema_failure")
            if (comment_id, fingerprint["body_sha256"]) not in existing_disposition_bindings:
                disposition_lines.append(canonical_json_line_bytes(disposition))

        terminal_outcomes[str(comment_id)] = {
            "outcome_code": code,
            "evaluation_run_id": evaluation_run_id,
            "canonical_record_sha256": record_hash,
            "cleanup_eligible": False,
        }
        bindings.append(
            {
                "comment_id": comment_id,
                "created_at": fingerprint["created_at"],
                "updated_at": fingerprint["updated_at"],
                "body_sha256": fingerprint["body_sha256"],
                "outcome_code": code,
                "evaluation_run_id": evaluation_run_id,
                "canonical_record_sha256": record_hash,
                "cleanup_eligible": False,
            }
        )

    final_comments = queue_fetcher(config.repository_root)
    final_fingerprints, final_queue_hash = _queue_snapshot(final_comments)
    if first_queue_hash != final_queue_hash or first_fingerprints != final_fingerprints:
        raise ProcessorError("source_changed")

    final_records = preserved_records + admitted_records
    final_evaluations = _append_jsonl(authority_files["evaluations.jsonl"], new_record_lines)
    final_dispositions = _append_jsonl(authority_files["ledger/dispositions.jsonl"], disposition_lines)
    final_record_objects = _validate_json_lines(final_evaluations)
    final_disposition_objects = []
    for line in final_dispositions.decode("utf-8").splitlines():
        if line.strip():
            final_disposition_objects.append(
                json.loads(
                    line,
                    parse_constant=_reject_nonfinite_constant,
                )
            )

    readme_text = authority_files["README.md"].decode("utf-8")
    scorecard_text = authority_files["scorecard.md"].decode("utf-8")
    expected_readme, expected_scorecard, manifest = expected_files_for_records(
        resolved_evaluations(final_record_objects),
        readme_text,
        scorecard_text,
        queued_evaluations=[],
    )
    readme_bytes = expected_readme.encode("utf-8")
    scorecard_bytes = expected_scorecard.encode("utf-8")
    recommendation_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

    canonical_files = {
        "evaluations.jsonl": final_evaluations,
        "ledger/dispositions.jsonl": final_dispositions,
        "README.md": readme_bytes,
        "scorecard.md": scorecard_bytes,
        "analysis/model-recommendation.json": recommendation_bytes,
    }
    hashes = {
        "evaluations_jsonl": sha256_bytes(final_evaluations),
        "dispositions_jsonl": sha256_bytes(final_dispositions),
        "readme_md": sha256_bytes(readme_bytes),
        "scorecard_md": sha256_bytes(scorecard_bytes),
        "model_recommendation_json": sha256_bytes(recommendation_bytes),
    }
    latest_id = first_fingerprints[-1]["id"] if first_fingerprints else None
    latest_update = max(
        (item["updated_at"] for item in first_fingerprints if item["updated_at"]),
        default=None,
    )
    batch_receipt: Optional[Dict[str, Any]] = None
    receipt_bytes: Optional[bytes] = None
    candidate_files = dict(authority_files)
    candidate_files.update(canonical_files)
    if config.candidate_content_commit_sha is not None:
        for relative_path, expected in canonical_files.items():
            if read_git_object(
                config.repository_root,
                config.candidate_content_commit_sha,
                relative_path,
            ) != expected:
                raise ProcessorError("processor_integrity_failure")
        batch_receipt = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": config.batch_id,
            "batch_mode": config.operating_mode,
            "controller_run_id": config.controller_run_id,
            "base_sha": config.base_sha,
            "canonical_main_sha": config.canonical_main_sha,
            "candidate_content_commit_sha": config.candidate_content_commit_sha,
            "pr_number": config.pr_number,
            "source_issue_number": config.source_issue_number,
            "receipt_issue_number": config.receipt_issue_number,
            "source_comment_watermark": latest_id or 0,
            "full_queue_count": len(first_fingerprints),
            "latest_observed_comment_id": latest_id,
            "latest_observed_update_time": latest_update,
            "queue_snapshot_sha256": first_queue_hash,
            "source_comment_ids": [item["id"] for item in first_fingerprints],
            "source_body_sha256": {
                str(item["id"]): item["body_sha256"] for item in first_fingerprints
            },
            "selected_comment_ids": [item["id"] for item in first_fingerprints],
            "selected_comment_count": len(first_fingerprints),
            "terminal_outcome_count": len(terminal_outcomes),
            "terminal_outcomes": terminal_outcomes,
            "admitted_run_ids": admitted_run_ids,
            "accepted_record_proofs": admitted_record_proofs,
            "canonical_record_hashes": new_record_hashes,
            "canonical_hashes": hashes,
            "comment_bindings": bindings,
        }
        if any(RECEIPT_VALIDATOR.iter_errors(batch_receipt)):
            raise ProcessorError("processor_schema_failure")
        if not validate_batch_receipt_closure(batch_receipt):
            raise ProcessorError("processor_schema_failure")
        receipt_bytes = (
            json.dumps(batch_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        candidate_files[existing_receipt_path] = receipt_bytes

    with build_complete_candidate_tree(config.repository_root, candidate_files) as candidate_tree:
        _validate_candidate_tree(
            candidate_tree.path,
            candidate_files,
            final_record_objects,
            final_disposition_objects,
            batch_receipt,
        )
        if failure_hook:
            failure_hook("candidate_validation_complete", "")

    return candidate_files, {
        "status": "CANDIDATE_VALIDATED",
        "batch_id": config.batch_id,
        "full_queue_count": len(first_fingerprints),
        "selected_comment_count": len(first_fingerprints),
        "admitted_count": len(admitted_records),
        "terminal_count": len(terminal_outcomes),
        "snapshot_hash": first_queue_hash,
        "evaluations_sha256": hashes["evaluations_jsonl"],
        "record_hashes": new_record_hashes,
        "receipt_sha256": sha256_bytes(receipt_bytes) if receipt_bytes is not None else None,
        "receipt_sealed": receipt_bytes is not None,
        "candidate_files": tuple(sorted(candidate_files)),
    }


def process_batch(
    config: ProcessBatchConfig,
    *,
    failure_hook: Optional[Callable[[str, str], None]] = None,
    comments: Optional[List[Dict[str, Any]]] = None,
    queue_fetcher: Optional[Callable[[Path], List[Dict[str, Any]]]] = None,
    comment_fetcher: Optional[Callable[[int, Path], Dict[str, Any]]] = None,
    canonical_main_fetcher: Optional[Callable[[Path], str]] = None,
) -> Dict[str, Any]:
    candidate_files, evidence = build_batch_candidate(
        config,
        comments,
        failure_hook=failure_hook,
        queue_fetcher=queue_fetcher,
        comment_fetcher=comment_fetcher,
        canonical_main_fetcher=canonical_main_fetcher,
    )
    queue_fetcher = queue_fetcher or fetch_live_142_comments
    final_queue = queue_fetcher(config.repository_root)
    if config.batch_id == FROZEN_BATCH_ID:
        receipt = _frozen_policy_receipt(config)
        final_snapshot_hash = FrozenBatchPolicy.from_receipt(
            receipt
        ).verify_source(final_queue).snapshot_sha256
    else:
        _, final_snapshot_hash = _queue_snapshot(final_queue)
    if final_snapshot_hash != evidence["snapshot_hash"]:
        raise ProcessorError("source_changed")
    if config.dry_run:
        return {
            **evidence,
            "candidate_files": candidate_files,
            "status": "DRY_RUN_VALIDATED",
            "tracked_replacement": False,
        }
    if config.activation_mode != "reviewed-live":
        raise ProcessorError("processor_activation_denied")
    replace_tracked_files(config.repository_root, candidate_files, failure_hook=failure_hook)
    return {
        **evidence,
        "candidate_files": candidate_files,
        "status": "TRACKED_REPLACEMENT_COMMITTED",
        "tracked_replacement": True,
    }


def parse_cli(argv: Optional[List[str]] = None) -> ProcessBatchConfig:
    parser = argparse.ArgumentParser(prog="batch_processor")
    parser.add_argument("--mode", dest="operating_mode", choices=["initial", "incremental"], required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--canonical-main-sha", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--controller-run-id", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--candidate-content-commit-sha")
    parser.add_argument("--activation-mode", choices=["dry-run", "reviewed-live"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-issue-number", type=int, required=True)
    parser.add_argument("--receipt-issue-number", type=int, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--operator-intent", choices=["reviewed"])
    parser.add_argument("--reviewed-pr-state", choices=["open", "merged"])
    parser.add_argument("--merge-state", choices=["unmerged", "merged"])
    parser.add_argument("--checks-state", choices=["incomplete", "passed"])
    parser.add_argument("--review-state", choices=["blocking", "clear"])
    args = parser.parse_args(argv)
    config = ProcessBatchConfig(
        operating_mode=args.operating_mode,
        base_sha=args.base_sha,
        canonical_main_sha=args.canonical_main_sha,
        batch_id=args.batch_id,
        controller_run_id=args.controller_run_id,
        pr_number=args.pr_number,
        expected_head_sha=args.expected_head_sha,
        activation_mode=args.activation_mode,
        dry_run=args.dry_run,
        source_issue_number=args.source_issue_number,
        receipt_issue_number=args.receipt_issue_number,
        repository_root=args.repository_root,
        operator_intent=args.operator_intent,
        reviewed_pr_state=args.reviewed_pr_state,
        merge_state=args.merge_state,
        checks_state=args.checks_state,
        review_state=args.review_state,
        candidate_content_commit_sha=args.candidate_content_commit_sha,
    )
    _validate_config(config)
    return config


def main(argv: Optional[List[str]] = None) -> int:
    try:
        config = parse_cli(argv)
        result = process_batch(config)
        print(json.dumps({key: value for key, value in result.items() if key != "candidate_files"}, sort_keys=True))
        return 0
    except (ProcessorError, ValueError, OSError):
        print("processor_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
