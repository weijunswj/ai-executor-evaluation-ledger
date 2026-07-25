#!/usr/bin/env python3
"""Base-trusted validator for scheduled-review batch PRs.

Executed from the PR base checkout only. Validates candidate tree supplied
as --candidate-dir without executing any candidate-controlled code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RESTRICTED_FILES = [
    "scripts/check_public_safety.py",
    "scripts/rebuild_views.py",
    "scripts/validate_scheduled_review_candidate.py",
    "scheduled-review/RULES.md",
    "schema/review-job.schema.json",
    "schema/batch.schema.json",
    "schema/review-result.schema.json",
]

RESTRICTED_DIRS = [
    ".github/workflows/",
]

try:
    import jsonschema
except ImportError:
    jsonschema = None


def require_jsonschema() -> None:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: python -m pip install jsonschema")


def check_restricted_files(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    for path in RESTRICTED_FILES:
        base_path = ROOT / path
        cand_path = candidate_dir / path
        base_exists = base_path.is_file()
        cand_exists = cand_path.is_file()
        if base_exists != cand_exists:
            action = "added" if cand_exists else "deleted"
            errors.append(f"Restricted file {action} in candidate: {path}")
            continue
        if base_exists and cand_exists:
            if base_path.read_bytes() != cand_path.read_bytes():
                errors.append(f"Restricted file modified: {path}")
    for d in RESTRICTED_DIRS:
        base_dir = ROOT / d
        cand_dir = candidate_dir / d
        if base_dir.is_dir() and cand_dir.is_dir():
            base_files = {f.relative_to(base_dir): f.read_bytes() for f in base_dir.rglob("*") if f.is_file()}
            cand_files = {f.relative_to(cand_dir): f.read_bytes() for f in cand_dir.rglob("*") if f.is_file()}
            if base_files.keys() != cand_files.keys():
                errors.append(f"Restricted directory file set changed: {d}")
            else:
                for name in base_files:
                    if base_files[name] != cand_files[name]:
                        errors.append(f"Restricted file modified: {d}{name}")
        elif base_dir.is_dir() != cand_dir.is_dir():
            errors.append(f"Restricted directory added or removed: {d}")
    return errors


def check_jsonl_prefix(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    base_jsonl = ROOT / "evaluations.jsonl"
    cand_jsonl = candidate_dir / "evaluations.jsonl"
    if not base_jsonl.exists():
        return errors
    if not cand_jsonl.exists():
        errors.append("evaluations.jsonl missing in candidate")
        return errors
    base_bytes = base_jsonl.read_bytes()
    cand_bytes = cand_jsonl.read_bytes()
    if not cand_bytes.startswith(base_bytes):
        errors.append("evaluations.jsonl is not an exact byte prefix of the base")
    return errors


def check_unique_ids(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    cand_jsonl = candidate_dir / "evaluations.jsonl"
    if not cand_jsonl.exists():
        return errors
    seen: set[str] = set()
    for line_num, line in enumerate(cand_jsonl.read_text(encoding="utf-8").splitlines(), 1):
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
    cand_jsonl = candidate_dir / "evaluations.jsonl"
    if not cand_jsonl.exists():
        return errors
    suffix_start = (ROOT / "evaluations.jsonl").read_bytes()
    cand_bytes = cand_jsonl.read_bytes()
    if not cand_bytes.startswith(suffix_start):
        return errors
    suffix_bytes = cand_bytes[len(suffix_start):]

    suffix_ids: set[str] = set()
    for line in suffix_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = rec.get("run_id")
        if rid:
            suffix_ids.add(rid)
    if not suffix_ids and not suffix_bytes.strip():
        pass

    for job in manifest.get("frozen_jobs", []):
        if job.get("state") == "blocked":
            continue
        if job.get("operation_class") in ("controller_administration", "ledger_maintenance"):
            continue
        if job.get("evaluable_run") is False:
            continue
        rid = job.get("run_id")
        if rid and rid not in suffix_ids:
            errors.append(f"Evaluable job {job['review_job_id']} run_id {rid} not in candidate suffix")
    return errors


def check_public_safety_on_candidate(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    safety_script = ROOT / "scripts" / "check_public_safety.py"
    if not safety_script.exists():
        errors.append("check_public_safety.py not found in base")
        return errors
    result = subprocess.run(
        ["python", str(safety_script)],
        cwd=candidate_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        errors.append(f"Public Safety failed on candidate: {result.stderr.strip()[:500]}")
    return errors


def check_deterministic_views(candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    rebuild_script = ROOT / "scripts" / "rebuild_views.py"
    if not rebuild_script.exists():
        return errors
    result = subprocess.run(
        ["python", str(rebuild_script), "--check"],
        cwd=candidate_dir, capture_output=True, text=True,
    )
    if result.returncode != 0:
        errors.append(f"Generated views not deterministic: {result.stderr.strip()[:500]}")
    return errors


def check_rulebook_consistency(manifest: dict[str, Any], candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    cand_rulebook = candidate_dir / "scheduled-review" / "RULES.md"
    if not cand_rulebook.exists():
        return errors
    result = subprocess.run(
        ["git", "hash-object", str(cand_rulebook)],
        cwd=candidate_dir, capture_output=True, text=True,
    )
    cand_sha = result.stdout.strip()
    frozen_sha = manifest.get("rulebook_sha", "")
    if cand_sha and frozen_sha and cand_sha != frozen_sha:
        errors.append(f"Rulebook SHA mismatch: candidate={cand_sha[:12]} manifest={frozen_sha[:12]}")
    return errors


def check_schema_revisions(manifest: dict[str, Any], candidate_dir: Path) -> list[str]:
    errors: list[str] = []
    for schema_name in ["review-job", "batch", "review-result"]:
        schema_path = candidate_dir / "schema" / f"{schema_name}.schema.json"
        if schema_path.exists():
            result = subprocess.run(
                ["git", "hash-object", str(schema_path)],
                cwd=candidate_dir, capture_output=True, text=True,
            )
            if result.stdout.strip():
                pass
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate scheduled-review candidate batch PR")
    parser.add_argument("--candidate-dir", required=True, help="Path to candidate tree")
    parser.add_argument("--base-sha", help="Base commit SHA (for workflow use)")
    parser.add_argument("--head-sha", help="Head commit SHA (for workflow use)")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).resolve()
    if not candidate_dir.is_dir():
        print(f"Candidate directory not found: {candidate_dir}", file=sys.stderr)
        return 1

    try:
        require_jsonschema()
    except RuntimeError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2

    all_errors: list[str] = []

    all_errors.extend(check_restricted_files(candidate_dir))
    all_errors.extend(check_jsonl_prefix(candidate_dir))
    all_errors.extend(check_unique_ids(candidate_dir))
    all_errors.extend(check_public_safety_on_candidate(candidate_dir))
    all_errors.extend(check_deterministic_views(candidate_dir))

    manifest_dirs = list((candidate_dir / "scheduled-review" / "batches").rglob("*/manifest.json"))
    for mf in manifest_dirs:
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            all_errors.append(f"Cannot read manifest: {mf}")
            continue
        all_errors.extend(check_manifest_coverage(manifest, candidate_dir))
        all_errors.extend(check_rulebook_consistency(manifest, candidate_dir))
        all_errors.extend(check_schema_revisions(manifest, candidate_dir))

    if all_errors:
        print(f"Validation failed ({len(all_errors)} errors):", file=sys.stderr)
        for error in all_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Candidate batch validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
