#!/usr/bin/env python3
"""Seal one public-safe review result for a frozen batch job."""

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


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


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


def seal_result(
    manifest: dict[str, Any],
    review_job_id: str,
    result_type: str,
    verdict: str | None = None,
    weighted_score_5: float | None = None,
    evaluation_record: dict[str, Any] | None = None,
    blocked_reason: str | None = None,
    is_correction: bool = False,
    correction_target_run_id: str | None = None,
) -> dict[str, Any]:
    job = find_job_in_manifest(manifest, review_job_id)
    if job is None:
        raise ValueError(f"Job {review_job_id} not found in batch manifest")

    now = datetime.now(SGT).isoformat()

    result: dict[str, Any] = {
        "schema_version": 1,
        "result_type": result_type,
        "review_job_id": review_job_id,
        "batch_id": manifest["batch_id"],
        "reviewed_at": now,
        "rulebook_sha": manifest["rulebook_sha"],
        "verdict": verdict,
        "weighted_score_5": weighted_score_5,
        "evaluation_record": evaluation_record,
        "blocked_reason": blocked_reason,
        "run_id": job.get("run_id"),
        "provider": job.get("provider"),
        "model": job.get("model"),
        "canonical_reasoning_level": job.get("canonical_reasoning_level"),
        "observed_reasoning_mode": job.get("observed_reasoning_mode"),
        "subject_alias": job.get("subject_alias"),
        "operation_class": job.get("operation_class"),
        "is_correction": is_correction,
        "correction_target_run_id": correction_target_run_id,
    }

    result_schema = load_schema("review-result")
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema:
        validator = jsonschema.Draft202012Validator(result_schema)
        errors = list(validator.iter_errors(result))
        if errors:
            raise ValueError("Result fails schema validation: " + "; ".join(str(e.message) for e in errors))

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
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    job_entry = find_job_in_manifest(manifest, review_job_id)
    if job_entry is None:
        return False

    if result["result_type"] == "evaluated":
        job_entry["state"] = "reviewed"
        job_entry["verdict"] = result.get("verdict")
        job_entry["reviewed_at"] = result["reviewed_at"]
        manifest["reviewed_count"] = manifest.get("reviewed_count", 0) + 1
    elif result["result_type"] == "blocked":
        job_entry["state"] = "blocked"
        job_entry["blocked_reason"] = result.get("blocked_reason")
        job_entry["public_safe_blocked_reason"] = result.get("blocked_reason")
        job_entry["reviewed_at"] = result["reviewed_at"]
        manifest["blocked_count"] = manifest.get("blocked_count", 0) + 1
    elif result["result_type"] == "administrative":
        job_entry["state"] = "reviewed"
        job_entry["reviewed_at"] = result["reviewed_at"]

    total = len(manifest["frozen_jobs"])
    reviewed = sum(1 for j in manifest["frozen_jobs"] if j["state"] in ("reviewed", "blocked", "superseded"))
    if reviewed == 0:
        manifest["state"] = "frozen"
    elif reviewed < total:
        manifest["state"] = "partially_reviewed"
    else:
        manifest["state"] = "reviewing"

    manifest["updated_at"] = result["reviewed_at"]

    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", str(result_path.relative_to(ROOT)), str(manifest_path.relative_to(ROOT))],
        cwd=ROOT,
        check=True,
    )

    commit_msg = f"Seal result for {review_job_id}: {result.get('verdict') or result['result_type']}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=ROOT, check=True)

    result_sha_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    subprocess.run(["git", "push", remote, branch_name], cwd=ROOT, check=True)

    result_remote = subprocess.run(
        ["git", "ls-remote", remote, f"refs/heads/{branch_name}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if not result_remote:
        raise RuntimeError(f"Remote ref refs/heads/{branch_name} not found after push")
    remote_sha = result_remote.split()[0]
    if remote_sha != result_sha_before:
        raise RuntimeError(
            f"Remote head {remote_sha[:12]} does not match pushed commit {result_sha_before[:12]}"
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
    parser.add_argument("--blocked-reason")
    parser.add_argument("--is-correction", action="store_true")
    parser.add_argument("--correction-target")
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args()

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
            manifest,
            args.review_job_id,
            args.result_type,
            verdict=args.verdict,
            weighted_score_5=args.score,
            evaluation_record=evaluation_record,
            blocked_reason=args.blocked_reason,
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

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
