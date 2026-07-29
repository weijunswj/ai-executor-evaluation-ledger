"""Read-only post-merge verification and operator-gated receipt preparation.

Source comments are retained.  This module has no source-comment mutation path;
future publication is an explicit injected operator action.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import jsonschema

from scripts.processor.common import (
    ProcessorError,
    safe_author_hash,
    sha256_bytes,
    validate_batch_receipt_closure,
    valid_author_login,
    valid_git_sha,
    valid_identifier,
)

ROOT = Path(__file__).resolve().parents[2]
EVALUATION_SCHEMA_PATH = ROOT / "schema" / "evaluation.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
EVALUATION_SCHEMA = json.loads(EVALUATION_SCHEMA_PATH.read_text(encoding="utf-8"))
RECEIPT_SCHEMA = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
EVALUATION_VALIDATOR = jsonschema.Draft202012Validator(
    EVALUATION_SCHEMA,
    format_checker=jsonschema.FormatChecker(),
)
RECEIPT_VALIDATOR = jsonschema.Draft202012Validator(
    RECEIPT_SCHEMA,
    format_checker=jsonschema.FormatChecker(),
)
RECORDED_MARKER = "<!-- ledger-recorded:v1 -->"


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


@dataclass(frozen=True)
class CleanupConfig:
    batch_id: str
    canonical_merge_sha: str
    canonical_main_sha: str
    expected_head_sha: str
    pr_number: int
    source_issue_number: int
    receipt_issue_number: int
    activation_mode: str
    operator_intent: str
    pr_state: str
    merge_state: str
    checks_state: str
    review_state: str
    recorded_receipt_status: str
    repository_root: Path


def _safe_failure(code: str) -> ProcessorError:
    return ProcessorError(code)


def _validate_config(config: CleanupConfig) -> None:
    if not valid_identifier(config.batch_id):
        raise _safe_failure("processor_invalid_contract")
    if not all(valid_git_sha(value) for value in (
        config.canonical_merge_sha,
        config.canonical_main_sha,
        config.expected_head_sha,
    )):
        raise _safe_failure("processor_invalid_contract")
    if not isinstance(config.pr_number, int) or config.pr_number <= 0:
        raise _safe_failure("processor_invalid_contract")
    if config.source_issue_number != 142 or config.receipt_issue_number != 143:
        raise _safe_failure("processor_invalid_contract")
    if config.activation_mode not in {"dry-run", "reviewed-live"}:
        raise _safe_failure("processor_invalid_contract")
    if config.activation_mode == "reviewed-live" and config.operator_intent != "reviewed":
        raise _safe_failure("processor_activation_denied")
    if config.pr_state not in {"open", "closed"}:
        raise _safe_failure("processor_invalid_contract")
    if config.merge_state not in {"unmerged", "merged"}:
        raise _safe_failure("processor_invalid_contract")
    if config.checks_state not in {"incomplete", "passed"}:
        raise _safe_failure("processor_invalid_contract")
    if config.review_state not in {"blocking", "clear", "unresolved_actionable"}:
        raise _safe_failure("processor_invalid_contract")
    if config.recorded_receipt_status not in {"absent", "present_matching", "conflicting", "unverified"}:
        raise _safe_failure("processor_invalid_contract")
    if not config.repository_root.exists():
        raise _safe_failure("processor_invalid_contract")


def _gh_get_json(path: str, repository_root: Path) -> Any:
    result = subprocess.run(
        ["gh", "api", path],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise _safe_failure("cleanup_source_unavailable")
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError):
        raise _safe_failure("cleanup_source_unavailable")
    return value


def _gh_get_paginated(path: str, repository_root: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", "api", path, "--paginate", "--slurp"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise _safe_failure("cleanup_source_unavailable")
    try:
        pages = json.loads(result.stdout)
    except (TypeError, ValueError):
        raise _safe_failure("cleanup_source_unavailable")
    if not isinstance(pages, list):
        raise _safe_failure("cleanup_source_unavailable")
    flattened: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, list):
            flattened.extend(item for item in page if isinstance(item, dict))
    return flattened


def _gh_get_threads(config: CleanupConfig) -> list[dict[str, Any]]:
    query = (
        "query($owner:String!,$repo:String!,$number:Int!,$cursor:String){"
        "repository(owner:$owner,name:$repo){pullRequest(number:$number){"
        "reviewThreads(first:100,after:$cursor){nodes{isResolved,isOutdated}"
        "pageInfo{hasNextPage,endCursor}}}}}"
    )
    nodes: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        cursor_arg = "null" if cursor is None else cursor
        result = subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={query}",
                "-F", "owner=weijunswj",
                "-F", "repo=ai-executor-evaluation-ledger",
                "-F", f"number={config.pr_number}",
                "-F", f"cursor={cursor_arg}",
            ],
            cwd=config.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise _safe_failure("cleanup_source_unavailable")
        try:
            value = json.loads(result.stdout)
            connection = value["data"]["repository"]["pullRequest"]["reviewThreads"]
            page_nodes = connection["nodes"]
            page_info = connection["pageInfo"]
        except (KeyError, TypeError, ValueError):
            raise _safe_failure("cleanup_source_unavailable")
        nodes.extend(node for node in page_nodes if isinstance(node, dict))
        if not page_info.get("hasNextPage"):
            return nodes
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise _safe_failure("cleanup_source_unavailable")
        cursor = next_cursor


def _recorded_receipt_status(batch_id: str, comments: list[dict[str, Any]]) -> str:
    matches = 0
    malformed = 0
    for comment in comments:
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(RECORDED_MARKER):
            continue
        raw = body[len(RECORDED_MARKER):].lstrip(" \t\r\n")
        try:
            value, end = json.JSONDecoder(parse_constant=_reject_nonfinite_constant).raw_decode(raw)
        except (TypeError, ValueError):
            malformed += 1
            continue
        if raw[end:].strip() or not isinstance(value, dict):
            malformed += 1
            continue
        if value.get("batch_id") == batch_id:
            matches += 1
    if malformed or matches > 1:
        return "conflicting"
    return "present_matching" if matches == 1 else "absent"


def _readback_live_authority(config: CleanupConfig) -> Dict[str, Any]:
    """Read PR, main, checks, reviews, threads and #143 without mutation."""

    pr = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/pulls/{config.pr_number}",
        config.repository_root,
    )
    main_ref = _gh_get_json(
        "repos/weijunswj/ai-executor-evaluation-ledger/git/ref/heads/main",
        config.repository_root,
    )
    check_runs = _gh_get_paginated(
        f"repos/weijunswj/ai-executor-evaluation-ledger/commits/{config.canonical_main_sha}/check-runs?per_page=100",
        config.repository_root,
    )
    reviews = _gh_get_paginated(
        f"repos/weijunswj/ai-executor-evaluation-ledger/pulls/{config.pr_number}/reviews?per_page=100",
        config.repository_root,
    )
    threads = _gh_get_threads(config)
    receipt_comments = _gh_get_paginated(
        "repos/weijunswj/ai-executor-evaluation-ledger/issues/143/comments?per_page=100",
        config.repository_root,
    )
    check_state = "passed" if check_runs and all(
        item.get("status") == "completed"
        and item.get("conclusion") in {"success", "neutral", "skipped"}
        for item in check_runs
    ) else "incomplete"
    review_state = "blocking" if any(
        str(item.get("state", "")).upper() in {"CHANGES_REQUESTED", "PENDING"}
        for item in reviews
    ) else "clear"
    if any(not item.get("isResolved") and not item.get("isOutdated") for item in threads):
        review_state = "unresolved_actionable"
    state = str(pr.get("state", "")).lower()
    merged = pr.get("merged_at") is not None
    head_sha = pr.get("head", {}).get("sha") if isinstance(pr.get("head"), dict) else None
    merge_sha = pr.get("merge_commit_sha")
    main_sha = main_ref.get("object", {}).get("sha") if isinstance(main_ref.get("object"), dict) else None
    if state not in {"open", "closed"} or not isinstance(head_sha, str) or not isinstance(main_sha, str):
        raise _safe_failure("cleanup_authority_unverified")
    return {
        "pr_state": state,
        "merge_state": "merged" if merged and merge_sha == main_sha else "unmerged",
        "checks_state": check_state,
        "review_state": review_state,
        "expected_head_sha": head_sha,
        "canonical_merge_sha": merge_sha if isinstance(merge_sha, str) else "",
        "canonical_main_sha": main_sha,
        "recorded_receipt_status": _recorded_receipt_status(config.batch_id, receipt_comments),
    }


def _assert_live_authority(config: CleanupConfig, authority: Mapping[str, Any]) -> None:
    for field in (
        "pr_state",
        "merge_state",
        "checks_state",
        "review_state",
        "canonical_merge_sha",
        "expected_head_sha",
        "canonical_main_sha",
        "recorded_receipt_status",
    ):
        if authority.get(field) != getattr(config, field):
            raise _safe_failure("cleanup_authority_unverified")


def fetch_live_comment(comment_id: int, repository_root: Path = ROOT) -> Dict[str, Any]:
    """Read one retained #142 comment without exposing its body to callers."""

    if not isinstance(comment_id, int) or comment_id <= 0:
        raise _safe_failure("cleanup_source_unavailable")
    value = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}",
        repository_root,
    )
    if not isinstance(value, dict):
        raise _safe_failure("cleanup_source_unavailable")
    return value


def _load_batch(root: Path, batch_id: str) -> tuple[Dict[str, Any], bytes, str]:
    path = root / "ledger" / "receipts" / "batches" / f"{batch_id}.json"
    if not path.is_file():
        raise _safe_failure("cleanup_batch_unavailable")
    raw = path.read_bytes()
    try:
        batch = json.loads(raw.decode("utf-8"), parse_constant=_reject_nonfinite_constant)
    except (UnicodeDecodeError, ValueError):
        raise _safe_failure("cleanup_batch_unavailable")
    if not isinstance(batch, dict) or batch.get("receipt_type") != "batch":
        raise _safe_failure("cleanup_batch_unavailable")
    if any(RECEIPT_VALIDATOR.iter_errors(batch)):
        raise _safe_failure("cleanup_batch_unavailable")
    if batch.get("schema_version") == 2 and not validate_batch_receipt_closure(batch):
        raise _safe_failure("cleanup_batch_unavailable")
    return batch, raw, sha256_bytes(raw)


def _current_hashes(root: Path) -> Dict[str, str]:
    paths = {
        "evaluations_jsonl": root / "evaluations.jsonl",
        "dispositions_jsonl": root / "ledger" / "dispositions.jsonl",
        "readme_md": root / "README.md",
        "scorecard_md": root / "scorecard.md",
        "model_recommendation_json": root / "analysis" / "model-recommendation.json",
    }
    if any(not path.is_file() for path in paths.values()):
        raise _safe_failure("cleanup_canonical_unavailable")
    return {name: sha256_bytes(path.read_bytes()) for name, path in paths.items()}


def _record_hashes(root: Path, run_ids: list[str]) -> Dict[str, str]:
    wanted = set(run_ids)
    found: Dict[str, str] = {}
    path = root / "evaluations.jsonl"
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=_reject_nonfinite_constant)
        except (UnicodeDecodeError, ValueError):
            raise _safe_failure("cleanup_canonical_unavailable")
        if isinstance(value, dict) and value.get("run_id") in wanted:
            run_id = value["run_id"]
            if run_id in found:
                raise _safe_failure("cleanup_canonical_unavailable")
            found[run_id] = sha256_bytes(line)
    if set(found) != wanted:
        raise _safe_failure("cleanup_canonical_unavailable")
    return found


def _record_identity_proofs(root: Path, run_ids: list[str]) -> Dict[str, Dict[str, Any]]:
    wanted = set(run_ids)
    found: Dict[str, Dict[str, Any]] = {}
    path = root / "evaluations.jsonl"
    for line in path.read_bytes().splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=_reject_nonfinite_constant)
        except (UnicodeDecodeError, ValueError):
            raise _safe_failure("cleanup_canonical_unavailable")
        if not isinstance(value, dict) or value.get("run_id") not in wanted:
            continue
        run_id = value["run_id"]
        if run_id in found or value.get("record_type") != "evaluation":
            raise _safe_failure("cleanup_canonical_unavailable")
        if any(EVALUATION_VALIDATOR.iter_errors(value)):
            raise _safe_failure("cleanup_canonical_unavailable")
        found[run_id] = {
            "provider": value["provider"],
            "model": value["model"],
            "outcome": value["outcome"],
            "weighted_score_5": value["weighted_score_5"],
        }
    if set(found) != wanted:
        raise _safe_failure("cleanup_canonical_unavailable")
    return found


def _retained_comment_evidence(
    batch: Mapping[str, Any],
    root: Path,
    fetcher: Callable[[int, Path], Dict[str, Any]],
) -> tuple[list[int], bool]:
    retained: list[int] = []
    verified = True
    expected_hashes = batch.get("source_body_sha256", {})
    expected_bindings = {
        int(binding["comment_id"]): binding
        for binding in batch.get("comment_bindings", [])
        if isinstance(binding, dict) and isinstance(binding.get("comment_id"), int)
    }
    for raw_id in batch.get("source_comment_ids", []):
        comment_id = int(raw_id)
        try:
            comment = fetcher(comment_id, root)
            body = comment.get("body") if isinstance(comment, dict) else None
            actual_id = comment.get("id") if isinstance(comment, dict) else None
            actual_updated = comment.get("updated_at") if isinstance(comment, dict) else None
            actual_created = comment.get("created_at") if isinstance(comment, dict) else None
            actual_user = comment.get("user") if isinstance(comment, dict) else None
            actual_login = actual_user.get("login") if isinstance(actual_user, dict) else None
            binding = expected_bindings.get(comment_id)
            expected_author_hash = binding.get("author_sha256") if isinstance(binding, dict) else None
            if expected_author_hash is None and isinstance(binding, dict):
                expected_author_hash = safe_author_hash(binding.get("author"))
            if (
                actual_id != comment_id
                or not isinstance(body, str)
                or not isinstance(binding, dict)
                or not valid_author_login(actual_login)
                or safe_author_hash(actual_login) != expected_author_hash
                or actual_created != binding.get("created_at")
                or actual_updated != binding.get("updated_at")
            ):
                verified = False
                retained.append(comment_id)
                continue
            if sha256_bytes(body.encode("utf-8")) != expected_hashes.get(str(comment_id)):
                verified = False
            retained.append(comment_id)
        except ProcessorError:
            verified = False
            retained.append(comment_id)
    return retained, verified


def prepare_cleanup_receipt(
    config: CleanupConfig,
    *,
    fetcher: Callable[[int, Path], Dict[str, Any]] = fetch_live_comment,
    authority_reader: Optional[Callable[[CleanupConfig], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Prove the post-merge state and return a non-published v2 receipt."""

    _validate_config(config)
    authority = authority_reader(config) if authority_reader is not None else _readback_live_authority(config)
    _assert_live_authority(config, authority)
    batch, batch_bytes, batch_hash = _load_batch(config.repository_root, config.batch_id)
    legacy_batch = batch.get("schema_version") != 2
    current_hashes = _current_hashes(config.repository_root)
    record_hashes = _record_hashes(config.repository_root, batch.get("admitted_run_ids", []))
    record_proofs = _record_identity_proofs(config.repository_root, batch.get("admitted_run_ids", []))
    retained_ids, retention_verified = _retained_comment_evidence(
        batch,
        config.repository_root,
        fetcher,
    )

    batch_record_hashes = dict(batch.get("canonical_record_hashes", {}))
    if legacy_batch:
        batch_record_hashes = {
            binding["evaluation_run_id"]: binding["canonical_record_sha256"]
            for binding in batch.get("comment_bindings", [])
            if isinstance(binding, dict)
            and binding.get("classification") == "admitted"
            and isinstance(binding.get("evaluation_run_id"), str)
            and isinstance(binding.get("canonical_record_sha256"), str)
        }
    canonical_verified = (
        not legacy_batch
        and config.pr_state == "closed"
        and config.merge_state == "merged"
        and config.canonical_merge_sha == config.canonical_main_sha
        and config.expected_head_sha == batch.get("expected_head_sha")
        and current_hashes == batch.get("canonical_hashes")
        and record_hashes == batch_record_hashes
        and record_proofs == batch.get("accepted_record_proofs", {})
    )
    receipt_verified = config.recorded_receipt_status in {"absent", "present_matching"}
    review_verified = config.checks_state == "passed" and config.review_state == "clear"
    post_merge_verified = canonical_verified and retention_verified and receipt_verified and review_verified
    branch_eligible = post_merge_verified and config.recorded_receipt_status == "present_matching"
    reason = "eligible" if branch_eligible else "receipt_unverified"
    if config.pr_state != "closed":
        reason = "open_pr"
    elif config.merge_state != "merged":
        reason = "not_merged"
    elif not retention_verified:
        reason = "source_retention_unverified"
    elif not review_verified:
        reason = "checks_unverified" if config.checks_state != "passed" else "review_unverified"
    elif not receipt_verified:
        reason = "receipt_unverified"
    elif not canonical_verified:
        reason = "canonical_unverified"

    receipt = {
        "schema_version": 2,
        "receipt_type": "cleanup",
        "cleanup_status": "verified" if post_merge_verified else "blocked",
        "batch_id": config.batch_id,
        "canonical_merge_sha": config.canonical_merge_sha,
        "canonical_main_sha": config.canonical_main_sha,
        "expected_head_sha": config.expected_head_sha,
        "pr_number": config.pr_number,
        "source_issue_number": config.source_issue_number,
        "receipt_issue_number": config.receipt_issue_number,
        "canonical_hashes": current_hashes,
        "canonical_record_hashes": record_hashes,
        "canonical_record_proofs": record_proofs,
        "source_comment_ids": list(batch.get("source_comment_ids", [])),
        "source_body_sha256": dict(batch.get("source_body_sha256", {})),
        "retained_comment_ids": retained_ids,
        "source_retention_verified": retention_verified,
        "recorded_receipt_status": config.recorded_receipt_status,
        "branch_cleanup_eligible": branch_eligible,
        "branch_cleanup_reason": reason,
        "publication_status": "pending_operator_publication",
        "platform_limitation_code": "web_orchestrator_publication_required",
        "batch_receipt_sha256": batch_hash,
        "batch_receipt_bytes_sha256": sha256_bytes(batch_bytes),
    }
    if any(RECEIPT_VALIDATOR.iter_errors(receipt)):
        raise _safe_failure("cleanup_schema_failure")
    return receipt


def publish_cleanup_receipt(
    receipt: Mapping[str, Any],
    *,
    activation_mode: str,
    operator_intent: str,
    publisher: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Use an explicit future operator adapter; never publish implicitly."""

    if activation_mode != "reviewed-live" or operator_intent != "reviewed":
        raise _safe_failure("processor_activation_denied")
    if receipt.get("cleanup_status") != "verified":
        raise _safe_failure("processor_activation_denied")
    if receipt.get("recorded_receipt_status") != "absent":
        raise _safe_failure("processor_activation_denied")
    if publisher is None:
        return {"status": "PENDING_OPERATOR_PUBLICATION", "platform_limitation_code": "web_orchestrator_publication_required"}
    result = publisher(receipt)
    if not isinstance(result, Mapping):
        raise _safe_failure("cleanup_publication_failed")
    return dict(result)


def run_cleanup(
    config: CleanupConfig,
    *,
    fetcher: Callable[[int, Path], Dict[str, Any]] = fetch_live_comment,
    authority_reader: Optional[Callable[[CleanupConfig], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run verification only; no tracked write, source mutation, or publication."""

    receipt = prepare_cleanup_receipt(config, fetcher=fetcher, authority_reader=authority_reader)
    return {
        "status": "VERIFIED" if receipt["cleanup_status"] == "verified" else "BLOCKED",
        "receipt": receipt,
        "source_comments_retained": receipt["source_retention_verified"],
        "publication_attempted": False,
        "branch_cleanup_eligible": receipt["branch_cleanup_eligible"],
    }


def parse_cli(argv: Optional[list[str]] = None) -> CleanupConfig:
    parser = argparse.ArgumentParser(prog="cleanup_workflow")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--canonical-merge-sha", required=True)
    parser.add_argument("--canonical-main-sha", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--source-issue-number", required=True, type=int)
    parser.add_argument("--receipt-issue-number", required=True, type=int)
    parser.add_argument("--activation-mode", choices=["dry-run", "reviewed-live"], required=True)
    parser.add_argument("--operator-intent", choices=["unreviewed", "reviewed"], required=True)
    parser.add_argument("--pr-state", choices=["open", "closed"], required=True)
    parser.add_argument("--merge-state", choices=["unmerged", "merged"], required=True)
    parser.add_argument("--checks-state", choices=["incomplete", "passed"], required=True)
    parser.add_argument("--review-state", choices=["blocking", "clear", "unresolved_actionable"], required=True)
    parser.add_argument("--recorded-receipt-status", choices=["absent", "present_matching", "conflicting", "unverified"], required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args(argv)
    config = CleanupConfig(**vars(args))
    _validate_config(config)
    return config


def main(argv: Optional[list[str]] = None) -> int:
    try:
        config = parse_cli(argv)
        result = run_cleanup(config)
        print(json.dumps({"status": result["status"], "publication_attempted": False}, sort_keys=True))
        return 0 if result["status"] == "VERIFIED" else 1
    except (ProcessorError, OSError, ValueError):
        print("cleanup_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
