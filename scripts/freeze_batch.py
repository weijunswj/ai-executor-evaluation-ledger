#!/usr/bin/env python3
"""Freeze pending review jobs into a new scheduled-review batch with atomic branch creation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SGT = timezone(timedelta(hours=8))

BATCH_BRANCH_RE = re.compile(r"^scheduled-review/batch-(?P<date>[0-9]{8})-(?P<seq>[0-9]{3})$")

try:
    import jsonschema
except ImportError:
    jsonschema = None


def require_jsonschema() -> None:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: python -m pip install jsonschema")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_against_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    require_jsonschema()
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}" for e in validator.iter_errors(data)]


def canonicalise_job(job: dict[str, Any]) -> bytes:
    return json.dumps(job, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def accepted_body_sha256(job: dict[str, Any]) -> str:
    return hashlib.sha256(canonicalise_job(job)).hexdigest()


def git_rulebook_sha() -> tuple[str, str]:
    result = subprocess.run(
        ["git", "hash-object", "scheduled-review/RULES.md"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    rulebook_sha = result.stdout.strip()
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    head_sha = result.stdout.strip()
    return rulebook_sha, head_sha


def next_batch_id(existing_branches: list[str]) -> str:
    today = datetime.now(SGT).strftime("%Y%m%d")
    seq = 1
    for branch in existing_branches:
        match = BATCH_BRANCH_RE.match(branch)
        if match and match.group("date") == today:
            num = int(match.group("seq"))
            if num >= seq:
                seq = num + 1
    return f"BATCH-{today}-{seq:03d}"


def batch_branch_name(batch_id: str) -> str:
    parts = batch_id.split("-")
    return f"scheduled-review/batch-{parts[1]}-{parts[2]}"


def check_clean_worktree() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    if result.stdout.strip():
        raise RuntimeError("Working tree is not clean")


def verify_base_sha(expected_sha: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    if result.stdout.strip() != expected_sha:
        raise RuntimeError(f"HEAD {result.stdout.strip()[:12]} does not match expected base {expected_sha[:12]}")


def create_batch(
    jobs: list[dict[str, Any]],
    batch_id: str,
    branch_name: str,
    base_sha: str,
    rulebook_sha: str,
    rulebook_commit: str,
) -> dict[str, Any]:
    require_jsonschema()
    now = datetime.now(SGT).isoformat()
    job_schema = load_schema("review-job")
    batch_schema = load_schema("batch")

    seen_job_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    frozen_jobs: list[dict[str, Any]] = []

    for job in jobs:
        errors = validate_against_schema(job, job_schema)
        if errors:
            raise ValueError(f"Job {job.get('review_job_id', '?')} fails schema: {'; '.join(errors)}")

        jid = job["review_job_id"]
        rid = job.get("run_id")
        if jid in seen_job_ids:
            raise ValueError(f"Duplicate review_job_id: {jid}")
        if rid and rid in seen_run_ids:
            raise ValueError(f"Duplicate run_id: {rid}")
        seen_job_ids.add(jid)
        if rid:
            seen_run_ids.add(rid)

        sha = accepted_body_sha256(job)
        entry: dict[str, Any] = {
            "review_job_id": jid,
            "accepted_body_sha256": sha,
            "state": "pending",
            "run_id": rid,
            "provider": job.get("provider"),
            "model": job.get("model"),
            "task_class": job.get("task_class"),
            "difficulty": job.get("difficulty"),
            "subject_alias": job.get("subject_alias"),
            "operation_class": job.get("operation_class"),
            "evaluable_run": job.get("evaluable_run"),
            "dependency_job_id": job.get("dependency_job_id"),
            "supersedes_job_id": job.get("supersedes_job_id"),
            "verdict": None,
            "reviewed_at": None,
            "blocked_reason": None,
        }
        frozen_jobs.append(entry)

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "batch_id": batch_id,
        "state": "frozen",
        "created_at": now,
        "updated_at": now,
        "rulebook_sha": rulebook_sha,
        "rulebook_commit": rulebook_commit,
        "rulebook_path": "scheduled-review/RULES.md",
        "base_main_sha": base_sha,
        "branch_name": branch_name,
        "frozen_jobs": frozen_jobs,
        "reviewed_count": 0,
        "blocked_count": 0,
        "pr_number": None,
        "proposed_policy_amendments": None,
        "completed_at": None,
        "merge_commit": None,
    }

    errors = validate_against_schema(manifest, batch_schema)
    if errors:
        raise ValueError("Manifest fails schema validation: " + "; ".join(errors))

    return manifest


def commit_and_push_batch(manifest: dict[str, Any], branch_name: str, remote: str = "origin") -> str:
    batch_id = manifest["batch_id"]
    base_sha = manifest["base_main_sha"]

    check_clean_worktree()
    verify_base_sha(base_sha)

    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=ROOT, check=True,
    )

    manifest_dir = ROOT / "scheduled-review" / "batches" / batch_id
    results_dir = manifest_dir / "results"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", str(manifest_path.relative_to(ROOT))],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"Freeze batch {batch_id}"],
        cwd=ROOT, check=True,
    )
    pushed_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()

    subprocess.run(
        ["git", "push", "-u", remote, branch_name],
        cwd=ROOT, check=True,
    )

    result = subprocess.run(
        ["git", "ls-remote", remote, f"refs/heads/{branch_name}"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    remote_sha = result.stdout.strip().split()[0] if result.stdout.strip() else ""

    if remote_sha != pushed_sha:
        raise RuntimeError(
            f"Remote head {remote_sha[:12]} does not match pushed commit {pushed_sha[:12]}"
        )

    return pushed_sha


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze pending review jobs into a batch")
    parser.add_argument("--jobs-file", help="JSON file containing an array of review-job objects")
    parser.add_argument("--remote", default="origin", help="Remote name")
    parser.add_argument("--dry-run", action="store_true", help="Print manifest without creating branch")
    args = parser.parse_args()

    if not args.jobs_file:
        print("--jobs-file is required", file=sys.stderr)
        return 1

    try:
        require_jsonschema()
    except RuntimeError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2

    try:
        jobs = json.loads(Path(args.jobs_file).read_text(encoding="utf-8"))
        if not isinstance(jobs, list):
            raise ValueError("jobs-file must contain a JSON array")
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"Failed to load jobs: {exc}", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["git", "ls-remote", "--heads", args.remote, "refs/heads/scheduled-review/batch-*"],
        cwd=ROOT, capture_output=True, text=True,
    )
    existing_branches = []
    for line in result.stdout.splitlines():
        if line.strip():
            parts = line.split("\t")
            if len(parts) == 2:
                existing_branches.append(parts[1].replace("refs/heads/", ""))

    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()

    rulebook_sha, rulebook_commit = git_rulebook_sha()
    batch_id = next_batch_id(existing_branches)
    branch_name = batch_branch_name(batch_id)

    try:
        manifest = create_batch(jobs, batch_id, branch_name, base_sha, rulebook_sha, rulebook_commit)
    except (ValueError, RuntimeError) as exc:
        print(f"Batch creation failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    try:
        pushed_sha = commit_and_push_batch(manifest, branch_name, args.remote)
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Commit/push failed: {exc}", file=sys.stderr)
        return 1

    print(f"Batch {batch_id} frozen on branch {branch_name} at {pushed_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
