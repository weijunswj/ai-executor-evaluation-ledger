#!/usr/bin/env python3
"""Assemble a completed scheduled-review batch: validate JSONL suffix, rebuild views, prepare PR."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "evaluations.jsonl"

try:
    import jsonschema
except ImportError:
    jsonschema = None


def require_jsonschema() -> None:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required. Install with: python -m pip install jsonschema")


def load_manifest() -> dict[str, Any]:
    batches_dir = ROOT / "scheduled-review" / "batches"
    manifests = list(batches_dir.glob("*/manifest.json"))
    if not manifests:
        raise RuntimeError("No batch manifest found")
    if len(manifests) > 1:
        raise RuntimeError("Multiple batch manifests found")
    return json.loads(manifests[0].read_text(encoding="utf-8"))


def load_results(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    batch_id = manifest["batch_id"]
    results_dir = ROOT / "scheduled-review" / "batches" / batch_id / "results"
    results: dict[str, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        results[result["review_job_id"]] = result
    return results


def verify_coverage(manifest: dict[str, Any], results: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for job in manifest["frozen_jobs"]:
        jid = job["review_job_id"]
        if jid not in results:
            errors.append(f"Missing result for {jid}")
            continue
        result = results[jid]
        if result.get("review_job_id") != jid:
            errors.append(f"Result identity mismatch for {jid}")
            continue
        if result.get("batch_id") != manifest["batch_id"]:
            errors.append(f"Result batch_id mismatch for {jid}")
            continue
        if result.get("rulebook_sha") != manifest.get("rulebook_sha"):
            errors.append(f"Result rulebook_sha mismatch for {jid}")

        is_evaluable = job.get("evaluable_run") and job.get("operation_class") not in (
            "controller_administration", "ledger_maintenance",
        )
        is_evaluable = is_evaluable and job.get("evaluable_run") is not False

        if job["state"] == "reviewed" and is_evaluable:
            if result.get("result_type") != "evaluated":
                errors.append(f"Job {jid} reviewed but result is {result.get('result_type')}")
            if not result.get("evaluation_record"):
                errors.append(f"Job {jid} is evaluable but has no evaluation_record")
            if result.get("run_id") != job.get("run_id"):
                errors.append(f"Job {jid} run_id mismatch with result")
            if result.get("provider") != job.get("provider"):
                errors.append(f"Job {jid} provider mismatch with result")
            if result.get("model") != job.get("model"):
                errors.append(f"Job {jid} model mismatch with result")
        elif job["state"] == "blocked":
            if result.get("result_type") != "blocked":
                errors.append(f"Job {jid} blocked but result is {result.get('result_type')}")
        elif job.get("operation_class") in ("controller_administration", "ledger_maintenance"):
            if result.get("result_type") != "administrative":
                errors.append(f"Job {jid} administrative but result is {result.get('result_type')}")
    return errors


def deterministic_order(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = []
    for jid in sorted(results.keys()):
        result = results[jid]
        if result.get("result_type") == "evaluated" and result.get("evaluation_record"):
            ordered.append(result)
    return ordered


def load_base_jsonl(base_sha: str) -> str:
    result = subprocess.run(
        ["git", "cat-file", "-p", f"{base_sha}:evaluations.jsonl"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return result.stdout


def append_ledger(
    base_content: str,
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
    base_sha: str,
) -> tuple[str, list[str]]:
    errors: list[str] = []

    actual_base = load_base_jsonl(base_sha)
    current = LEDGER_PATH.read_text(encoding="utf-8")
    if not current.startswith(actual_base):
        errors.append("Current evaluations.jsonl does not start with exact base content from base_main_sha")

    existing_ids: set[str] = set()
    for line in actual_base.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = rec.get("run_id")
        if rid:
            existing_ids.add(rid)

    new_lines: list[str] = []
    seen_batch_ids: set[str] = set()

    for record in records:
        rec = record["evaluation_record"]
        rid = rec.get("run_id", "")
        jid = record["review_job_id"]
        if rid in existing_ids or rid in seen_batch_ids:
            errors.append(f"Duplicate run_id {rid} in {jid}")
            continue
        seen_batch_ids.add(rid)
        new_lines.append(json.dumps(rec, ensure_ascii=False))

    if errors:
        return "", errors

    if base_content and not base_content.endswith("\n"):
        base_content += "\n"
    new_content = base_content + "\n".join(new_lines) + "\n"

    expected = actual_base
    if expected and not expected.endswith("\n"):
        expected += "\n"
    suffix = "\n".join(new_lines) + "\n"
    if new_content != expected + suffix:
        errors.append("Assembled content does not equal exact base + deterministic suffix")

    if errors:
        return "", errors

    return new_content, []


def check_public_safety() -> bool:
    result = subprocess.run(
        ["python", str(ROOT / "scripts" / "check_public_safety.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0


def rebuild_views() -> bool:
    result = subprocess.run(
        ["python", str(ROOT / "scripts" / "rebuild_views.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False
    result = subprocess.run(
        ["python", str(ROOT / "scripts" / "rebuild_views.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0


def generate_pr_body(manifest: dict[str, Any], results: dict[str, dict[str, Any]]) -> str:
    batch_id = manifest["batch_id"]
    lines = [
        f"# Scheduled review batch {batch_id}",
        "",
        "## Batch summary",
        "",
        f"- **Batch ID**: `{batch_id}`",
        f"- **Base main**: `{manifest['base_main_sha']}`",
        f"- **Rulebook**: `{manifest['rulebook_sha']}` (commit `{manifest.get('rulebook_commit', '?')[:12]}`)",
        f"- **Jobs frozen**: {len(manifest['frozen_jobs'])}",
        f"- **Reviewed**: {manifest.get('reviewed_count', 0)}",
        f"- **Blocked**: {manifest.get('blocked_count', 0)}",
        "",
        "## Results",
        "",
    ]

    lines.append("| Review Job ID | Verdict | Score | Model |")
    lines.append("|---|---|---|---|")

    for jid in sorted(results.keys()):
        r = results[jid]
        verdict = r.get("verdict", r.get("result_type", "")).upper()
        score = f"{r.get('weighted_score_5', ''):.2f}/5" if r.get("weighted_score_5") is not None else "-"
        model = r.get("model", "-")
        lines.append(f"| {jid} | {verdict} | {score} | {model} |")

    lines.extend(["", "## Blocked jobs", ""])
    has_blocked = False
    for jid in sorted(results.keys()):
        r = results[jid]
        if r.get("result_type") == "blocked":
            has_blocked = True
            lines.append(f"- **{jid}**: {r.get('blocked_reason_code', 'unknown')}")
    if not has_blocked:
        lines.append("None.")

    lines.extend([
        "",
        "## Administrative classification",
        "",
        "- `operation_class: controller_administration`",
        "- `evaluable_run: false`",
        "- This PR performs no new grading of the reviewer.",
        "- This PR must not create another review job.",
        "",
        "## Manual exact-head merge required.",
        "",
        "Do not auto-merge. The controller must perform final exact-head review before merge.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble a completed batch for PR")
    parser.add_argument("--dry-run", action="store_true", help="Validate without committing")
    parser.add_argument("--commit", action="store_true", help="Commit the assembled batch")
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

    results = load_results(manifest)
    errors = verify_coverage(manifest, results)
    if errors:
        print("Coverage errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    ordered = deterministic_order(results)
    base_content = LEDGER_PATH.read_text(encoding="utf-8")

    new_content, append_errors = append_ledger(
        base_content, ordered, manifest, manifest["base_main_sha"],
    )
    if append_errors:
        print("Append errors:", file=sys.stderr)
        for e in append_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Assembly valid. Would append:")
        for rec in ordered:
            rid = rec["evaluation_record"].get("run_id", "?")
            jid = rec["review_job_id"]
            print(f"  {jid}: {rid}")
        return 0

    LEDGER_PATH.write_text(new_content, encoding="utf-8", newline="\n")

    if not rebuild_views():
        print("View rebuild failed", file=sys.stderr)
        return 1

    if not check_public_safety():
        print("Public Safety check failed", file=sys.stderr)
        return 1

    if args.commit:
        branch_name = manifest["branch_name"]
        subprocess.run(
            ["git", "add", "evaluations.jsonl", "README.md", "scorecard.md"],
            cwd=ROOT, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Assemble batch {manifest['batch_id']}"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "push", args.remote, branch_name], cwd=ROOT, check=True)

    pr_body = generate_pr_body(manifest, results)
    print(pr_body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
