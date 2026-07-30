"""Read-only post-merge verification and operator-gated receipt preparation.

Source comments are retained.  This module has no source-comment mutation path;
future publication is an explicit injected operator action.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import jsonschema

from scripts.processor.common import (
    ProcessorError,
    canonical_json_bytes,
    sha256_bytes,
    validate_batch_receipt_closure,
    valid_git_sha,
    valid_identifier,
)
from scripts.processor.github_cli import gh_json
from scripts.validate_receipts import (
    ReceiptValidationError,
    validate_batch_receipt_object,
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
REQUIRED_CHECK_PRODUCERS = (
    {
        "producer": "ci_push",
        "workflow_path": ".github/workflows/ci.yml",
        "event": "push",
        "job_names": ("validate",),
    },
    {
        "producer": "ci_pull_request",
        "workflow_path": ".github/workflows/ci.yml",
        "event": "pull_request",
        "job_names": ("validate",),
    },
    {
        "producer": "public_safety",
        "workflow_path": ".github/workflows/public-safety.yml",
        "event": "pull_request",
        "job_names": ("Scan public ledger",),
    },
    {
        "producer": "codeql",
        "workflow_path": "dynamic/github-code-scanning/codeql",
        "event": "dynamic",
        "job_names": ("Analyze (python)", "Analyze (actions)"),
    },
)
CANONICAL_PATHS = {
    "evaluations_jsonl": "evaluations.jsonl",
    "dispositions_jsonl": "ledger/dispositions.jsonl",
    "readme_md": "README.md",
    "scorecard_md": "scorecard.md",
    "model_recommendation_json": "analysis/model-recommendation.json",
}


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


def _git_output(repository_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise _safe_failure("processor_cleanup_canonical_unavailable")
    return result.stdout


def _verify_local_canonical_checkout(repository_root: Path, canonical_main_sha: str) -> None:
    _git_output(repository_root, "cat-file", "-e", f"{canonical_main_sha}^{{commit}}")
    head = _git_output(repository_root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if head != canonical_main_sha:
        raise _safe_failure("processor_cleanup_authority_unverified")


def _git_object_bytes(repository_root: Path, commit_sha: str, relative_path: str) -> bytes:
    if relative_path.startswith(("/", "\\")) or ".." in Path(relative_path).parts:
        raise _safe_failure("processor_cleanup_canonical_unavailable")
    return _git_output(repository_root, "show", f"{commit_sha}:{relative_path}")


def _gh_get_json(path: str, repository_root: Path) -> Any:
    return gh_json(
        repository_root,
        [path],
        failure_code="cleanup_source_unavailable",
    )


def _gh_get_paginated(path: str, repository_root: Path) -> list[dict[str, Any]]:
    pages = gh_json(
        repository_root,
        [path],
        failure_code="cleanup_source_unavailable",
        paginate=True,
    )
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
        value = gh_json(
            config.repository_root,
            [
                "graphql",
                "-f", f"query={query}",
                "-F", "owner=weijunswj",
                "-F", "repo=ai-executor-evaluation-ledger",
                "-F", f"number={config.pr_number}",
                "-F", f"cursor={cursor_arg}",
            ],
            failure_code="cleanup_source_unavailable",
        )
        try:
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


def _required_check_attempts(
    head_sha: str,
    workflow_runs: list[dict[str, Any]],
    jobs_by_attempt: Mapping[tuple[int, int], list[dict[str, Any]]],
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Select one latest exact run attempt for every required producer."""

    evidence: dict[str, dict[str, Any]] = {}
    for required in REQUIRED_CHECK_PRODUCERS:
        candidates: list[dict[str, Any]] = []
        for run in workflow_runs:
            if (
                run.get("path") != required["workflow_path"]
                or run.get("event") != required["event"]
            ):
                continue
            required_fields = (
                run.get("id"),
                run.get("workflow_id"),
                run.get("run_number"),
                run.get("run_attempt"),
                run.get("check_suite_id"),
            )
            if (
                run.get("head_sha") != head_sha
                or not all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in required_fields)
                or not isinstance(run.get("status"), str)
                or not isinstance(run.get("conclusion"), (str, type(None)))
            ):
                return "incomplete", {}
            candidates.append(run)
        if not candidates:
            return "incomplete", {}
        latest_order = max((run["run_number"], run["run_attempt"]) for run in candidates)
        latest = [
            run
            for run in candidates
            if (run["run_number"], run["run_attempt"]) == latest_order
        ]
        if len(latest) != 1:
            return "incomplete", {}
        run = latest[0]
        jobs = jobs_by_attempt.get((run["id"], run["run_attempt"]))
        if not isinstance(jobs, list):
            return "incomplete", {}
        selected_jobs: dict[str, dict[str, Any]] = {}
        for job_name in required["job_names"]:
            matching = [job for job in jobs if job.get("name") == job_name]
            if len(matching) != 1:
                return "incomplete", {}
            job = matching[0]
            if (
                not isinstance(job.get("id"), int)
                or isinstance(job.get("id"), bool)
                or job["id"] <= 0
                or job.get("run_id") != run["id"]
                or job.get("head_sha") != head_sha
                or not isinstance(job.get("status"), str)
                or not isinstance(job.get("conclusion"), (str, type(None)))
            ):
                return "incomplete", {}
            selected_jobs[job_name] = job
        evidence[required["producer"]] = {
            "workflow_id": run["workflow_id"],
            "workflow_path": run["path"],
            "event": run["event"],
            "run_id": run["id"],
            "run_number": run["run_number"],
            "run_attempt": run["run_attempt"],
            "check_suite_id": run["check_suite_id"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "jobs": {
                name: {
                    "job_id": job["id"],
                    "status": job["status"],
                    "conclusion": job["conclusion"],
                }
                for name, job in sorted(selected_jobs.items())
            },
        }
        if (
            run["status"] != "completed"
            or run["conclusion"] != "success"
            or any(
                job["status"] != "completed" or job["conclusion"] != "success"
                for job in selected_jobs.values()
            )
        ):
            return "incomplete", evidence
    return "passed", evidence


def _parse_recorded_receipt_body(body: Any) -> Optional[dict[str, Any]]:
    if not isinstance(body, str) or not body.startswith(RECORDED_MARKER):
        return None
    raw = body[len(RECORDED_MARKER):].lstrip(" \t\r\n")
    try:
        value, end = json.JSONDecoder(parse_constant=_reject_nonfinite_constant).raw_decode(raw)
    except (TypeError, ValueError):
        raise _safe_failure("processor_cleanup_receipt_invalid")
    if raw[end:].strip() or not isinstance(value, dict):
        raise _safe_failure("processor_cleanup_receipt_invalid")
    if any(RECEIPT_VALIDATOR.iter_errors(value)):
        raise _safe_failure("processor_cleanup_receipt_invalid")
    expected_body = RECORDED_MARKER + "\n" + canonical_json_bytes(value).decode("utf-8")
    if body != expected_body:
        raise _safe_failure("processor_cleanup_receipt_invalid")
    return value


def _receipt_matches_authority(value: Mapping[str, Any], config: CleanupConfig) -> bool:
    expected = {
        "receipt_type": "cleanup",
        "cleanup_status": "verified",
        "batch_id": config.batch_id,
        "canonical_merge_sha": config.canonical_merge_sha,
        "canonical_main_sha": config.canonical_main_sha,
        "expected_head_sha": config.expected_head_sha,
        "pr_number": config.pr_number,
        "source_issue_number": config.source_issue_number,
        "receipt_issue_number": config.receipt_issue_number,
        "source_retention_verified": True,
    }
    return all(value.get(field) == wanted for field, wanted in expected.items())


def _recorded_receipt_status(config: CleanupConfig, comments: list[dict[str, Any]]) -> str:
    matches = 0
    for comment in comments:
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(RECORDED_MARKER):
            continue
        try:
            value = _parse_recorded_receipt_body(body)
        except ProcessorError:
            return "conflicting"
        if value is not None and value.get("batch_id") == config.batch_id:
            if not _receipt_matches_authority(value, config):
                return "conflicting"
            matches += 1
    if matches > 1:
        return "conflicting"
    return "present_matching" if matches == 1 else "absent"


def _readback_live_authority(config: CleanupConfig) -> Dict[str, Any]:
    """Read PR, main, checks, reviews, threads and #143 without mutation."""

    pr = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/pulls/{config.pr_number}",
        config.repository_root,
    )
    head_sha = pr.get("head", {}).get("sha") if isinstance(pr.get("head"), dict) else None
    if not valid_git_sha(head_sha):
        raise _safe_failure("processor_cleanup_authority_unverified")
    main_ref = _gh_get_json(
        "repos/weijunswj/ai-executor-evaluation-ledger/git/ref/heads/main",
        config.repository_root,
    )
    raw_commit = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/commits/{head_sha}",
        config.repository_root,
    )
    receipt_path = f"ledger/receipts/batches/{config.batch_id}.json"
    raw_receipt = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/contents/{receipt_path}?ref={head_sha}",
        config.repository_root,
    )
    workflow_runs_value = _gh_get_json(
        f"repos/weijunswj/ai-executor-evaluation-ledger/actions/runs?head_sha={head_sha}&per_page=100",
        config.repository_root,
    )
    workflow_runs = (
        workflow_runs_value.get("workflow_runs")
        if isinstance(workflow_runs_value, dict)
        else None
    )
    if not isinstance(workflow_runs, list):
        raise _safe_failure("processor_cleanup_authority_unverified")
    jobs_by_attempt: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for run in workflow_runs:
        if not isinstance(run, dict):
            raise _safe_failure("processor_cleanup_authority_unverified")
        if not any(
            run.get("path") == required["workflow_path"]
            and run.get("event") == required["event"]
            for required in REQUIRED_CHECK_PRODUCERS
        ):
            continue
        run_id = run.get("id")
        attempt = run.get("run_attempt")
        if (
            not isinstance(run_id, int)
            or isinstance(run_id, bool)
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
        ):
            raise _safe_failure("processor_cleanup_authority_unverified")
        jobs_value = _gh_get_json(
            f"repos/weijunswj/ai-executor-evaluation-ledger/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100",
            config.repository_root,
        )
        jobs = jobs_value.get("jobs") if isinstance(jobs_value, dict) else None
        if not isinstance(jobs, list):
            raise _safe_failure("processor_cleanup_authority_unverified")
        jobs_by_attempt[(run_id, attempt)] = jobs
    reviews = _gh_get_paginated(
        f"repos/weijunswj/ai-executor-evaluation-ledger/pulls/{config.pr_number}/reviews?per_page=100",
        config.repository_root,
    )
    threads = _gh_get_threads(config)
    receipt_comments = _gh_get_paginated(
        "repos/weijunswj/ai-executor-evaluation-ledger/issues/143/comments?per_page=100",
        config.repository_root,
    )
    check_state, required_check_attempts = _required_check_attempts(
        head_sha,
        workflow_runs,
        jobs_by_attempt,
    )
    review_state = "blocking" if any(
        str(item.get("state", "")).upper() in {"CHANGES_REQUESTED", "PENDING"}
        for item in reviews
    ) else "clear"
    if any(not item.get("isResolved") and not item.get("isOutdated") for item in threads):
        review_state = "unresolved_actionable"
    state = str(pr.get("state", "")).lower()
    merged = pr.get("merged_at") is not None
    merge_sha = pr.get("merge_commit_sha")
    main_sha = main_ref.get("object", {}).get("sha") if isinstance(main_ref.get("object"), dict) else None
    if state not in {"open", "closed"} or not valid_git_sha(main_sha):
        raise _safe_failure("processor_cleanup_authority_unverified")
    parents = raw_commit.get("parents")
    files = raw_commit.get("files")
    encoded_receipt = raw_receipt.get("content")
    if (
        not isinstance(parents, list)
        or not isinstance(files, list)
        or raw_receipt.get("type") != "file"
        or raw_receipt.get("encoding") != "base64"
        or not isinstance(encoded_receipt, str)
    ):
        raise _safe_failure("processor_cleanup_authority_unverified")
    try:
        raw_receipt_bytes = base64.b64decode(
            "".join(encoded_receipt.split()),
            validate=True,
        )
    except ValueError:
        raise _safe_failure("processor_cleanup_authority_unverified")
    return {
        "pr_state": state,
        "merge_state": "merged" if merged and merge_sha == main_sha else "unmerged",
        "checks_state": check_state,
        "review_state": review_state,
        "expected_head_sha": head_sha,
        "canonical_merge_sha": merge_sha if isinstance(merge_sha, str) else "",
        "canonical_main_sha": main_sha,
        "recorded_receipt_status": _recorded_receipt_status(config, receipt_comments),
        "raw_head_parent_shas": [
            item.get("sha") for item in parents if isinstance(item, dict)
        ],
        "raw_head_changed_paths": [
            item.get("filename") for item in files if isinstance(item, dict)
        ],
        "raw_head_receipt_sha256": sha256_bytes(raw_receipt_bytes),
        "required_check_attempts": required_check_attempts,
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


def _load_batch(root: Path, commit_sha: str, batch_id: str) -> tuple[Dict[str, Any], bytes, str]:
    raw = _git_object_bytes(
        root,
        commit_sha,
        f"ledger/receipts/batches/{batch_id}.json",
    )
    try:
        batch = json.loads(raw.decode("utf-8"), parse_constant=_reject_nonfinite_constant)
    except (UnicodeDecodeError, ValueError):
        raise _safe_failure("processor_cleanup_batch_unavailable")
    if not isinstance(batch, dict) or batch.get("receipt_type") != "batch":
        raise _safe_failure("processor_cleanup_batch_unavailable")
    if any(RECEIPT_VALIDATOR.iter_errors(batch)):
        raise _safe_failure("processor_cleanup_batch_unavailable")
    if batch.get("schema_version") == 2 and not validate_batch_receipt_closure(batch):
        raise _safe_failure("processor_cleanup_batch_unavailable")
    return batch, raw, sha256_bytes(raw)


def _verify_raw_head_receipt_seal(
    root: Path,
    raw_head_sha: str,
    batch: Mapping[str, Any],
    batch_bytes: bytes,
    authority: Mapping[str, Any],
) -> None:
    receipt_path = f"ledger/receipts/batches/{batch['batch_id']}.json"
    if {
        "raw_head_parent_shas",
        "raw_head_changed_paths",
        "raw_head_receipt_sha256",
    }.issubset(authority):
        if (
            authority["raw_head_parent_shas"]
            != [batch.get("candidate_content_commit_sha")]
            or authority["raw_head_changed_paths"] != [receipt_path]
            or authority["raw_head_receipt_sha256"] != sha256_bytes(batch_bytes)
        ):
            raise _safe_failure("processor_cleanup_authority_unverified")
        return
    _git_output(root, "cat-file", "-e", f"{raw_head_sha}^{{commit}}")
    parent_line = (
        _git_output(root, "rev-list", "--parents", "-n", "1", raw_head_sha)
        .decode("ascii")
        .strip()
        .split()
    )
    if len(parent_line) != 2 or parent_line[1] != batch.get("candidate_content_commit_sha"):
        raise _safe_failure("processor_cleanup_authority_unverified")
    changed = (
        _git_output(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            parent_line[1],
            raw_head_sha,
        )
        .decode("utf-8")
        .splitlines()
    )
    if changed != [receipt_path]:
        raise _safe_failure("processor_cleanup_authority_unverified")
    if _git_object_bytes(root, raw_head_sha, receipt_path) != batch_bytes:
        raise _safe_failure("processor_cleanup_authority_unverified")


def _current_hashes(root: Path, commit_sha: str) -> Dict[str, str]:
    return {
        name: sha256_bytes(_git_object_bytes(root, commit_sha, relative))
        for name, relative in CANONICAL_PATHS.items()
    }


def _record_hashes(evaluations_bytes: bytes, run_ids: list[str]) -> Dict[str, str]:
    wanted = set(run_ids)
    found: Dict[str, str] = {}
    for line in evaluations_bytes.splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=_reject_nonfinite_constant)
        except (UnicodeDecodeError, ValueError):
            raise _safe_failure("cleanup_canonical_unavailable")
        if isinstance(value, dict) and value.get("run_id") in wanted:
            run_id = value["run_id"]
            if run_id in found:
                raise _safe_failure("processor_cleanup_canonical_unavailable")
            if not line.endswith(b"\n"):
                raise _safe_failure("processor_cleanup_canonical_unavailable")
            found[run_id] = sha256_bytes(line)
    if set(found) != wanted:
        raise _safe_failure("processor_cleanup_canonical_unavailable")
    return found


def _record_identity_proofs(evaluations_bytes: bytes, run_ids: list[str]) -> Dict[str, Dict[str, Any]]:
    wanted = set(run_ids)
    found: Dict[str, Dict[str, Any]] = {}
    for line in evaluations_bytes.splitlines():
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
            raise _safe_failure("processor_cleanup_canonical_unavailable")
        if any(EVALUATION_VALIDATOR.iter_errors(value)):
            raise _safe_failure("processor_cleanup_canonical_unavailable")
        found[run_id] = {
            "provider": value["provider"],
            "model": value["model"],
            "outcome": value["outcome"],
            "weighted_score_5": value["weighted_score_5"],
        }
    if set(found) != wanted:
        raise _safe_failure("processor_cleanup_canonical_unavailable")
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
            binding = expected_bindings.get(comment_id)
            if (
                actual_id != comment_id
                or not isinstance(body, str)
                or not isinstance(binding, dict)
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
    _verify_local_canonical_checkout(config.repository_root, config.canonical_main_sha)
    authority = authority_reader(config) if authority_reader is not None else _readback_live_authority(config)
    _assert_live_authority(config, authority)
    batch, batch_bytes, batch_hash = _load_batch(
        config.repository_root,
        config.canonical_main_sha,
        config.batch_id,
    )
    try:
        validate_batch_receipt_object(
            config.repository_root,
            batch,
            authority_sha=config.canonical_main_sha,
        )
    except ReceiptValidationError:
        raise _safe_failure("processor_cleanup_batch_unavailable")
    _verify_raw_head_receipt_seal(
        config.repository_root,
        config.expected_head_sha,
        batch,
        batch_bytes,
        authority,
    )
    evaluations_bytes = _git_object_bytes(
        config.repository_root,
        config.canonical_main_sha,
        CANONICAL_PATHS["evaluations_jsonl"],
    )
    current_hashes = _current_hashes(config.repository_root, config.canonical_main_sha)
    record_hashes = _record_hashes(evaluations_bytes, batch.get("admitted_run_ids", []))
    record_proofs = _record_identity_proofs(evaluations_bytes, batch.get("admitted_run_ids", []))
    retained_ids, retention_verified = _retained_comment_evidence(
        batch,
        config.repository_root,
        fetcher,
    )

    batch_record_hashes = dict(batch.get("canonical_record_hashes", {}))
    canonical_verified = (
        config.pr_state == "closed"
        and config.merge_state == "merged"
        and config.canonical_merge_sha == config.canonical_main_sha
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
    publisher: Optional[Callable[[str], int]] = None,
    readback: Optional[Callable[[int], Mapping[str, Any]]] = None,
    comments_reader: Optional[Callable[[], list[dict[str, Any]]]] = None,
    authority_verifier: Optional[Callable[[Mapping[str, Any]], bool]] = None,
) -> Dict[str, Any]:
    """Publish only through an operator adapter followed by exact canonical read-back."""

    if activation_mode != "reviewed-live" or operator_intent != "reviewed":
        raise _safe_failure("processor_activation_denied")
    if receipt.get("cleanup_status") != "verified":
        raise _safe_failure("processor_activation_denied")
    if receipt.get("recorded_receipt_status") != "absent":
        raise _safe_failure("processor_activation_denied")
    if publisher is None:
        return {"status": "PENDING_OPERATOR_PUBLICATION", "platform_limitation_code": "web_orchestrator_publication_required"}
    if readback is None or comments_reader is None or authority_verifier is None:
        return {"status": "PENDING_OPERATOR_PUBLICATION", "platform_limitation_code": "publication_readback_required"}

    intended_body = RECORDED_MARKER + "\n" + canonical_json_bytes(dict(receipt)).decode("utf-8")
    try:
        locator = publisher(intended_body)
        if not isinstance(locator, int) or isinstance(locator, bool) or locator <= 0:
            raise ValueError("invalid_locator")
        comment = readback(locator)
        if not isinstance(comment, Mapping):
            raise ValueError("invalid_readback")
        issue_url = comment.get("issue_url")
        if (
            comment.get("id") != locator
            or comment.get("body") != intended_body
            or not isinstance(issue_url, str)
            or not issue_url.endswith("/issues/143")
        ):
            raise ValueError("mismatched_readback")
        parsed = _parse_recorded_receipt_body(comment.get("body"))
        if parsed != dict(receipt):
            raise ValueError("mismatched_receipt")
        comments = comments_reader()
        matching = [
            item for item in comments
            if isinstance(item, dict) and item.get("body") == intended_body
        ]
        if len(matching) != 1 or matching[0].get("id") != locator:
            raise ValueError("ambiguous_readback")
        if not authority_verifier(parsed):
            raise ValueError("authority_changed")
    except (OSError, ProcessorError, TypeError, ValueError):
        return {"status": "PENDING_OPERATOR_PUBLICATION", "platform_limitation_code": "publication_readback_unverified"}
    return {
        "status": "published",
        "comment_id": locator,
        "body_sha256": sha256_bytes(intended_body.encode("utf-8")),
    }


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
