#!/usr/bin/env python3
"""Base-trusted validator for scheduled-review batch PRs.

This script is executed from the PR base checkout. It validates the candidate
tree (supplied as --candidate-dir) without executing any candidate-controlled code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

RESTRICTED_PATHS = [
    ".github/workflows/",
    "scripts/check_public_safety.py",
    "scripts/rebuild_views.py",
    "scripts/validate_scheduled_review_candidate.py",
    "scheduled-review/RULES.md",
    "schema/review-job.schema.json",
    "schema/batch.schema.json",
    "schema/review-result.schema.json",
]


def check_restricted_paths(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    for restricted in RESTRICTED_PATHS:
        base_path = ROOT / restricted
        candidate_path = candidate_dir / restricted
        if restricted.endswith("/"):
            base_files = set()
            candidate_files = set()
            if base_path.is_dir():
                for f in base_path.rglob("*"):
                    if f.is_file():
                        base_files.add(str(f.relative_to(base_path)))
            if candidate_path.is_dir():
                for f in candidate_path.rglob("*"):
                    if f.is_file():
                        candidate_files.add(str(f.relative_to(candidate_path)))
            if base_files != candidate_files:
                errors.append(f"Restricted directory changed: {restricted}")
        else:
            if not base_path.exists() and candidate_path.exists():
                errors.append(f"Restricted file added in candidate: {restricted}")
            elif base_path.exists() and candidate_path.exists():
                base_content = base_path.read_bytes()
                candidate_content = candidate_path.read_bytes()
                if base_content != candidate_content:
                    errors.append(f"Restricted file modified: {restricted}")
    return errors


def check_jsonl_prefix(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    base_jsonl = ROOT / "evaluations.jsonl"
    candidate_jsonl = candidate_dir / "evaluations.jsonl"
    if not base_jsonl.exists():
        return []
    if not candidate_jsonl.exists():
        errors.append("evaluations.jsonl missing in candidate")
        return errors
    base_content = base_jsonl.read_text(encoding="utf-8")
    candidate_content = candidate_jsonl.read_text(encoding="utf-8")
    if not candidate_content.startswith(base_content):
        errors.append("evaluations.jsonl is not an exact prefix of the base")
    return errors


def check_unique_ids(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    candidate_jsonl = candidate_dir / "evaluations.jsonl"
    if not candidate_jsonl.exists():
        return []
    seen: set[str] = set()
    for line_num, line in enumerate(candidate_jsonl.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"evaluations.jsonl:{line_num}: invalid JSON")
            continue
        rid = rec.get("run_id")
        if not isinstance(rid, str) or not rid:
            errors.append(f"evaluations.jsonl:{line_num}: missing run_id")
            continue
        if rid in seen:
            errors.append(f"evaluations.jsonl:{line_num}: duplicate run_id {rid}")
        seen.add(rid)
    return errors


def check_manifest_coverage(manifest: dict[str, Any], candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    candidate_jsonl = candidate_dir / "evaluations.jsonl"
    if not candidate_jsonl.exists():
        return errors
    candidate_ids: set[str] = set()
    for line in candidate_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = rec.get("run_id")
        if rid:
            candidate_ids.add(rid)

    for job in manifest.get("frozen_jobs", []):
        if job.get("state") == "blocked":
            continue
        if job.get("operation_class") in ("controller_administration", "ledger_maintenance"):
            continue
        if not job.get("evaluable_run", True):
            continue
        rid = job.get("run_id")
        if rid and rid not in candidate_ids:
            errors.append(f"Evaluable job {job['review_job_id']} run_id {rid} not found in candidate JSONL")
    return errors


def check_no_private_data(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    result = subprocess.run(
        ["python", str(ROOT / "scripts" / "check_public_safety.py")],
        cwd=candidate_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f"Public Safety failed in candidate: {result.stderr.strip()}")
    return errors


def check_deterministic_views(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    candidate_readme = candidate_dir / "README.md"
    candidate_scorecard = candidate_dir / "scorecard.md"
    if not candidate_readme.exists() or not candidate_scorecard.exists():
        return errors

    result = subprocess.run(
        ["python", str(ROOT / "scripts" / "rebuild_views.py"), "--check"],
        cwd=candidate_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f"Generated views are not deterministic: {result.stderr.strip()}")
    return errors


def check_rulebook_consistency(manifest: dict[str, Any], candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    candidate_rulebook = candidate_dir / "scheduled-review" / "RULES.md"
    if not candidate_rulebook.exists():
        return errors
    result = subprocess.run(
        ["git", "hash-object", str(candidate_rulebook)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    candidate_sha = result.stdout.strip()
    frozen_sha = manifest.get("rulebook_sha", "")
    if candidate_sha and frozen_sha and candidate_sha != frozen_sha:
        errors.append(f"Rulebook SHA mismatch: candidate={candidate_sha[:12]} manifest={frozen_sha[:12]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate scheduled-review candidate batch PR")
    parser.add_argument("--candidate-dir", required=True, help="Path to candidate tree")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).resolve()
    if not candidate_dir.is_dir():
        print(f"Candidate directory not found: {candidate_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []

    all_errors.extend(check_restricted_paths(candidate_dir))
    all_errors.extend(check_jsonl_prefix(candidate_dir))
    all_errors.extend(check_unique_ids(candidate_dir))
    all_errors.extend(check_no_private_data(candidate_dir))
    all_errors.extend(check_deterministic_views(candidate_dir))

    manifest_path = candidate_dir / "scheduled-review" / "batches"
    manifests = list(manifest_path.rglob("*/manifest.json"))
    if manifests:
        for mf in manifests:
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                all_errors.append(f"Cannot read manifest: {mf}")
                continue
            all_errors.extend(check_manifest_coverage(manifest, candidate_dir))
            all_errors.extend(check_rulebook_consistency(manifest, candidate_dir))
    else:
        pass

    if all_errors:
        print(f"Validation failed ({len(all_errors)} errors):", file=sys.stderr)
        for error in all_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Candidate batch validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
