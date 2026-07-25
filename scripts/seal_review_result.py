#!/usr/bin/env python3
"""Seal one public-safe review result for a frozen batch job with remote push verification."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SGT = timezone(timedelta(hours=8))

try:
    import jsonschema
except ImportError:
    jsonschema = None

ALLOWED_BLOCKED_REASONS = {
    "intake_missing",
    "duplicate_job_id",
    "intake_body_changed",
    "invalid_schema",
    "missing_model_identity",
    "missing_source_revision",
    "conflicting_duplicate_run_id",
    "source_inaccessible",
    "source_head_missing",
    "private_evidence_unavailable",
    "material_evidence_conflict",
    "review_too_large",
    "dependent_job_blocked",
}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "frozen": {"reviewing"},
    "reviewing": {"partially_reviewed", "batch_pr_open", "blocked", "abandoned"},
    "partially_reviewed": {"batch_pr_open", "blocked", "abandoned"},
    "batch_pr_open": {"merged", "abandoned"},
    "merged": {"completed"},
    "completed": set(),
    "blocked": set(),
    "abandoned": set(),
}


def require_jsonschema() -> None:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: python -m pip install jsonschema")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_against_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    require_jsonschema()
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}" for e in validator.iter_errors(data)]


def load_manifest() -> dict[str, Any]:
    batches_dir = ROOT / "scheduled-review" / "batches"
    manifests = list(batches_dir.glob("*/manifest.json"))
    if not manifests:
        raise RuntimeError("No batch manifest found")
    if len(manifests) > 1:
        raise RuntimeError("Multiple batch manifests found")
    return json.loads(manifests[0].read_text(encoding="utf-8"))


def find_job_in_manifest(manifest: dict[str, Any], review_job_id: str) -> dict[str, Any] | None:
    for job in manifest["frozen_jobs"]:
        if job["review_job_id"] == review_job_id:
            return job
    return None


def recompute_counters(manifest: dict[str, Any]) -> tuple[int, int]:
    reviewed = 0
    blocked = 0
    for job in manifest["frozen_jobs"]:
        if job["state"] == "reviewed":
            reviewed += 1
        elif job["state"] == "blocked":
            blocked += 1
    return reviewed, blocked


def compute_next_state(manifest: dict[str, Any]) -> str:
    total = len(manifest["frozen_jobs"])
    reviewed, blocked = recompute_counters(manifest)
    done = reviewed + blocked
    current = manifest.get("state", "frozen")
    if done == 0:
        return current if current == "frozen" else "frozen"
    if done < total:
        if current not in ("frozen", "reviewing", "partially_reviewed"):
            return "partially_reviewed"
        return "partially_reviewed"
    if current in ("partially_reviewed", "reviewing"):
        return "reviewing"
    return current


def seal_result(
    manifest: dict[str, Any],
    review_job_id: str,
    result_type: str,
    verdict: str | None = None,
    weighted_score_5: float | None = None,
    evaluation_record: dict[str, Any] | None = None,
    blocked_reason_code: str | None = None,
    is_correction: bool = False,
    correction_target_run_id: str | None = None,
) -> dict[str, Any]:
    require_jsonschema()
    job = find_job_in_manifest(manifest, review_job_id)
    if job is None:
        raise ValueError(f"Job {review_job_id} not found in batch manifest")

    if result_type == "blocked":
        if not blocked_reason_code:
            raise ValueError("blocked_reason_code is required for blocked results")
        if blocked_reason_code not in ALLOWED_BLOCKED_REASONS:
            raise ValueError(f"blocked_reason_code '{blocked_reason_code}' is not in the allowlist")

    now = datetime.now(SGT).isoformat()

    result: dict[str, Any] = {
        "schema_version": 2,
        "result_type": result_type,
        "review_job_id": review_job_id,
        "batch_id": manifest["batch_id"],
        "reviewed_at": now,
        "rulebook_sha": manifest["rulebook_sha"],
        "verdict": verdict,
        "weighted_score_5": weighted_score_5,
        "evaluation_record": evaluation_record,
        "blocked_reason_code": blocked_reason_code,
        "run_id": job.get("run_id"),
        "provider": job.get("provider"),
        "model": job.get("model"),
        "subject_alias": job.get("subject_alias"),
        "operation_class": job.get("operation_class"),
        "is_correction": is_correction,
        "correction_target_run_id": correction_target_run_id,
    }

    result_schema = load_schema("review-result")
    errors = validate_against_schema(result, result_schema)
    if errors:
        raise ValueError("Result fails schema validation: " + "; ".join(errors))

    if result_type == "evaluated" and evaluation_record is not None:
        eval_schema_path = ROOT / "schema" / "evaluation.schema.json"
        eval_schema = json.loads(eval_schema_path.read_text(encoding="utf-8"))
        eval_errors = validate_against_schema(evaluation_record, eval_schema)
        if eval_errors:
            raise ValueError("Evaluation record fails schema validation: " + "; ".join(eval_errors))

    return result


def write_and_push(
    manifest: dict[str, Any],
    result: dict[str, Any],
    review_job_id: str,
    remote: str = "origin",
) -> bool:
    batch_id = manifest["batch_id"]
    branch_name = manifest["branch_name"]
    batch_dir = ROOT / "scheduled-review" / "batches" / batch_id
    results_dir = batch_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    result_path = results_dir / f"{review_job_id}.json"

    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        existing_bytes = json.dumps(existing, sort_keys=True, ensure_ascii=False).encode("utf-8")
        new_bytes = json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if existing_bytes == new_bytes:
            print(f"Idempotent replay for {review_job_id} — skipping")
            return True
        else:
            raise RuntimeError(
                f"Sealed result for {review_job_id} already exists with different content — replacement forbidden"
            )

    job_entry = find_job_in_manifest(manifest, review_job_id)
    if job_entry is None:
        return False

    previous_state = manifest.get("state", "frozen")

    if result["result_type"] == "evaluated" or result["result_type"] == "administrative":
        job_entry["state"] = "reviewed"
        job_entry["verdict"] = result.get("verdict")
        job_entry["reviewed_at"] = result["reviewed_at"]
    elif result["result_type"] == "blocked":
        job_entry["state"] = "blocked"
        job_entry["blocked_reason"] = result.get("blocked_reason_code")
        job_entry["reviewed_at"] = result["reviewed_at"]

    reviewed, blocked = recompute_counters(manifest)
    manifest["reviewed_count"] = reviewed
    manifest["blocked_count"] = blocked

    next_state = compute_next_state(manifest)
    valid_next = VALID_TRANSITIONS.get(previous_state, set())
    if next_state != previous_state and next_state not in valid_next:
        raise RuntimeError(f"Invalid lifecycle transition: {previous_state} -> {next_state}")
    manifest["state"] = next_state
    manifest["updated_at"] = result["reviewed_at"]

    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", str(result_path.relative_to(ROOT)), str(manifest_path.relative_to(ROOT))],
        cwd=ROOT, check=True,
    )
    commit_msg = f"Seal result for {review_job_id}: {result.get('verdict') or result['result_type']}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=ROOT, check=True)

    result_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()

    subprocess.run(["git", "push", remote, branch_name], cwd=ROOT, check=True)

    ls_result = subprocess.run(
        ["git", "ls-remote", remote, f"refs/heads/{branch_name}"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    if not ls_result.stdout.strip():
        raise RuntimeError(f"Remote ref refs/heads/{branch_name} not found after push")
    remote_sha = ls_result.stdout.strip().split()[0]
    if remote_sha != result_sha:
        raise RuntimeError(
            f"Remote head {remote_sha[:12]} does not match pushed commit {result_sha[:12]}"
        )

    print(f"Sealed and verified: {review_job_id} at {remote_sha[:12]}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal a review result for a batch job")
    parser.add_argument("review_job_id", help="Review job ID")
    parser.add_argument("--result-type", required=True, choices=["evaluated", "blocked", "administrative"])
    parser.add_argument("--verdict")
    parser.add_argument("--score", type=float)
    parser.add_argument("--evaluation-record", help="JSON file containing evaluation record")
    parser.add_argument("--blocked-reason-code", help="Allowlisted blocked reason code")
    parser.add_argument("--is-correction", action="store_true")
    parser.add_argument("--correction-target")
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args()

    try:
        require_jsonschema()
    except RuntimeError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2

    try:
        manifest = load_manifest()
    except RuntimeError as exc:
        print(f"Failed to load manifest: {exc}", file=sys.stderr)
        return 1

    evaluation_record = None
    if args.evaluation_record:
        try:
            evaluation_record = json.loads(Path(args.evaluation_record).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to load evaluation record: {exc}", file=sys.stderr)
            return 1

    try:
        result = seal_result(
            manifest, args.review_job_id, args.result_type,
            verdict=args.verdict, weighted_score_5=args.score,
            evaluation_record=evaluation_record,
            blocked_reason_code=args.blocked_reason_code,
            is_correction=args.is_correction,
            correction_target_run_id=args.correction_target,
        )
    except ValueError as exc:
        print(f"Failed to seal result: {exc}", file=sys.stderr)
        return 1

    try:
        success = write_and_push(manifest, result, args.review_job_id, args.remote)
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Push verification failed: {exc}", file=sys.stderr)
        return 1

    if not success:
        print(f"Failed to update manifest for {args.review_job_id}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
