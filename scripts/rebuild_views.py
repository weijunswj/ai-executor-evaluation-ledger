#!/usr/bin/env python3
"""Generate and verify the public ledger views from the append-only JSONL source and valid queued intake."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "evaluations.jsonl"
README_PATH = ROOT / "README.md"
SCORECARD_PATH = ROOT / "scorecard.md"
RECOMMENDATION_JSON_PATH = ROOT / "analysis" / "model-recommendation.json"
DISPLAY_LIMIT = 30

README_START = "<!-- GENERATED:README-SCORES:START -->"
README_END = "<!-- GENERATED:README-SCORES:END -->"
SCORECARD_START = "<!-- GENERATED:SCORECARD-RUNS:START -->"
SCORECARD_END = "<!-- GENERATED:SCORECARD-RUNS:END -->"

README_TITLE = "# AI Executor Evaluation Ledger"
SCORECARD_TITLE = "# Executor Scorecard"

CANONICAL_MODEL_MAP = {
    "MiMo 2.5 Pro": "MiMo 2.5 Pro",
    "Claude Opus 4.8": "Claude Opus 4.8",
    "Claude Opus 4.8 High": "Claude Opus 4.8",
    "Claude Opus 4.8 Ultra High": "Claude Opus 4.8",
    "Claude Opus 5": "Claude Opus 5",
    "Claude Opus 5 Max": "Claude Opus 5",
    "DeepSeek V4 Pro": "DeepSeek V4 Pro",
    "GPT-5.6 Sol": "GPT-5.6 Sol",
    "GPT-5.6 Sol Medium": "GPT-5.6 Sol",
    "GPT-5.6 Sol High": "GPT-5.6 Sol",
    "GPT-5.6 Sol Max": "GPT-5.6 Sol",
    "Qwen3.7 Plus": "Qwen3.7 Plus",
    "Gemini 3.1 Pro": "Gemini 3.1 Pro",
    "Gemini 3.6 Flash": "Gemini 3.6 Flash",
    "MiniMax M3": "MiniMax M3",
    "Qwen3.6 Plus": "Qwen3.6 Plus"
}

def fail(message: str) -> None:
    raise ValueError(message)

def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for line_number, raw_line in enumerate(LEDGER_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            fail(f"evaluations.jsonl:{line_number}: invalid JSON: {exc.msg}")
        if not isinstance(record, dict):
            fail(f"evaluations.jsonl:{line_number}: record must be an object")
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            fail(f"evaluations.jsonl:{line_number}: missing run_id")
        if run_id in seen_ids:
            fail(f"evaluations.jsonl:{line_number}: duplicate run_id {run_id}")
        seen_ids.add(run_id)
        records.append(record)

    return records

def resolved_evaluations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluations: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for record in records:
        record_type = record.get("record_type")
        if record_type == "evaluation":
            run_id = record["run_id"]
            evaluations[run_id] = copy.deepcopy(record)
            order.append(run_id)
        elif record_type != "correction":
            fail(f"{record['run_id']}: unsupported record_type {record_type!r}")

    for record in records:
        if record.get("record_type") != "correction":
            continue
        affected = record.get("affected_run_id")
        corrected = record.get("corrected_fields")
        if affected not in evaluations:
            fail(f"{record['run_id']}: unknown affected_run_id {affected!r}")
        if not isinstance(corrected, dict) or not corrected:
            fail(f"{record['run_id']}: corrected_fields must be a non-empty object")
        evaluations[affected].update(copy.deepcopy(corrected))

    result = [evaluations[run_id] for run_id in order]
    for record in result:
        record["model"] = canonical_model(record)
        record["evaluation_protocol"] = record.get("evaluation_protocol", "protocol_unknown")
        validate_evaluation(record)
    return result

def canonical_model(record: dict[str, Any]) -> str:
    raw_model = str(record.get("model") or "").strip()
    if raw_model in CANONICAL_MODEL_MAP:
        return CANONICAL_MODEL_MAP[raw_model]
    fail(f"{record.get('run_id')}: unmapped model {raw_model!r}")
    return raw_model

def validate_evaluation(record: dict[str, Any]) -> None:
    run_id = record["run_id"]
    required_strings = ("reviewed_at", "model", "task_class", "difficulty", "outcome", "subject_alias")
    for field in required_strings:
        if not isinstance(record.get(field), str) or not record[field].strip():
            fail(f"{run_id}: missing {field}")
    score = record.get("weighted_score_5")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 5:
        fail(f"{run_id}: weighted_score_5 must be between 0 and 5")
    if not isinstance(record.get("first_pass_accepted"), bool):
        fail(f"{run_id}: first_pass_accepted must be boolean")

def record_time(record: dict[str, Any]) -> datetime:
    try:
        dt_str = record["reviewed_at"].replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return datetime.min

def format_time(record: dict[str, Any]) -> str:
    value = record_time(record)
    if value == datetime.min:
        return str(record["reviewed_at"])
    suffix = " SGT" if value.utcoffset() == timedelta(hours=8) else ""
    return value.strftime("%d %b %Y %H:%M") + suffix

def title_case(value: str) -> str:
    return value.replace("-", " ").strip().title()

def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

def percentage(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{round(100 * numerator / denominator)}%"

def evidence_level(run_count: int, task_count: int) -> str:
    if run_count == 0:
        return "Formal backfill pending"
    if run_count <= 2:
        return "Anecdotal"
    if run_count <= 5:
        return "Provisional across mixed tasks" if task_count > 1 else "Provisional"
    if run_count <= 10:
        return "Moderate"
    return "Useful operating baseline"

def generate_recommendation_manifest(evaluations: list[dict[str, Any]], total_queued_count: int = 0) -> dict[str, Any]:
    gated_evals = [e for e in evaluations if e.get("evaluation_protocol") == "gated_v1"]

    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in gated_evals:
        by_model[e["model"]].append(e)

    model_stats = {}
    for model in sorted(by_model.keys()):
        items = by_model[model]
        n = len(items)
        avg = sum(float(x["weighted_score_5"]) for x in items) / n if n > 0 else 0.0
        first_pass_rate = sum(1 for x in items if x.get("first_pass_accepted")) / n if n > 0 else 0.0
        verdicts = defaultdict(int)
        for x in items:
            verdicts[str(x.get("outcome")).lower()] += 1

        subjects = len({x.get("subject_alias") for x in items})
        task_cohorts = len({(x.get("task_class"), x.get("difficulty")) for x in items})

        model_stats[model] = {
            "recorded_count": n,
            "queued_count": 0,
            "available_count": n,
            "average_score_5": round(avg, 2),
            "first_pass_rate": round(first_pass_rate, 2),
            "verdict_distribution": dict(sorted(verdicts.items())),
            "independent_subjects": subjects,
            "task_cohort_count": task_cohorts,
            "cited_run_ids": sorted([x["run_id"] for x in items])
        }

    # Deterministic timestamp based on latest evaluated record
    latest_dt = max((record_time(e) for e in evaluations if record_time(e) != datetime.min), default=None)
    gen_time = latest_dt.isoformat() if latest_dt else "2026-07-29T10:00:00Z"
    if not gen_time.endswith("Z") and "+" not in gen_time:
        gen_time += "Z"

    manifest = {
        "schema_version": 1,
        "generated_at": gen_time,
        "official_recorded_gated_evaluations": len(gated_evals),
        "total_queued_evaluations": total_queued_count,
        "total_available_evaluations": len(gated_evals) + total_queued_count,
        "model_statistics": model_stats,
        "material_limitations": [
            "Official ranking uses only comparable recorded gated_v1 evidence.",
            "Queued evidence contributes only to provisional non-ranking conclusions.",
            "Like-for-like task evidence takes priority over all-task averages."
        ]
    }
    return manifest

def render_recommendation_section(manifest: dict[str, Any]) -> str:
    stats = manifest.get("model_statistics", {})

    lines = [
        "## AI Model Recommendations & Operational Guidance",
        "",
        f"**Official Recorded Gated Evidence:** {manifest.get('official_recorded_gated_evaluations', 0)} runs | **Queued Intake:** {manifest.get('total_queued_evaluations', 0)} runs | **Total Available:** {manifest.get('total_available_evaluations', 0)} runs",
        "",
        "### Tested Model Summary & Like-for-Like Analysis",
        ""
    ]

    if not stats:
        lines.append("No comparable `gated_v1` recorded evaluations currently available. Official rankings will be updated upon recording gated evaluations.")
    else:
        # Sort models by average score descending, then model name ascending
        sorted_models = sorted(stats.items(), key=lambda x: (-x[1]["average_score_5"], x[0]))
        for model, info in sorted_models:
            lines.append(f"- **{model}**: Average Score **{info['average_score_5']:.2f}/5** across {info['recorded_count']} recorded run(s) ({info['independent_subjects']} independent subject/task family). First-pass acceptance: **{round(info['first_pass_rate'] * 100)}%**.")

    lines.extend([
        "",
        "> [!NOTE]",
        "> Recommendations are strictly grounded in empirical recorded `gated_v1` evidence. Queued intake is provisional and does not alter official recorded rankings."
    ])

    return "\n".join(lines)

def summary_table(evaluations: list[dict[str, Any]], *, include_flags: bool) -> str:
    gated_evals = [e for e in evaluations if e.get("evaluation_protocol") == "gated_v1"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in gated_evals:
        grouped[e["model"]].append(e)

    headers = [
        "Model",
        "Formal runs",
        "Average /5",
        "First-pass acceptance",
        "Safe final state verified",
    ]
    if include_flags:
        headers.append("Integrity/control flags")
    headers.append("Evidence level")

    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if index in {1, 2, 3, 4, 5} else "---" for index in range(len(headers))) + "|",
    ]

    # Sort models by gated_v1 average score descending, then model name ascending
    sorted_keys = sorted(grouped.keys(), key=lambda m: (-sum(float(x["weighted_score_5"]) for x in grouped[m]) / len(grouped[m]), m))

    for model in sorted_keys:
        model_records = grouped[model]
        run_count = len(model_records)
        average = f"{sum(float(item['weighted_score_5']) for item in model_records) / run_count:.2f}"
        first_pass = percentage(sum(item["first_pass_accepted"] for item in model_records), run_count)
        applicable = [r for r in model_records if r.get("safe_final_state_verified") is not None]
        safe_state = f"{sum(r.get('safe_final_state_verified') is True for r in applicable)}/{len(applicable)} applicable" if applicable else "-"
        task_count = len({(item["task_class"], item["difficulty"]) for item in model_records})
        evidence = evidence_level(run_count, task_count)
        flags = str(sum(len(item.get("integrity_and_control_flags", [])) for item in model_records))

        row: list[object] = [model, run_count, average, first_pass, safe_state]
        if include_flags:
            row.append(flags)
        row.append(evidence)
        lines.append("| " + " | ".join(markdown_cell(item) for item in row) + " |")

    return "\n".join(lines)

def task_table(evaluations: list[dict[str, Any]], *, heading: str) -> str:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in evaluations:
        key = (record["model"], record["task_class"], record["difficulty"])
        grouped[key].append(record)

    lines = [
        f"## {heading}",
        "",
        "| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    # Sort task rows by model name ascending, task class ascending, difficulty ascending
    for key in sorted(grouped.keys(), key=lambda x: (x[0], x[1], x[2])):
        model, task_class, difficulty = key
        items = grouped[key]
        average = sum(float(item["weighted_score_5"]) for item in items) / len(items)
        first_pass = percentage(sum(item["first_pass_accepted"] for item in items), len(items))
        confidence = evidence_level(len(items), 1)
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    model,
                    title_case(task_class),
                    title_case(difficulty),
                    len(items),
                    f"{average:.2f}",
                    first_pass,
                    confidence,
                )
            )
            + " |"
        )
    return "\n".join(lines)

def formal_runs_table(records: list[dict[str, Any]]) -> str:
    lines = [
        "## Formal evaluated runs",
        "",
        f"Newest first. This table displays at most {DISPLAY_LIMIT} formal evaluation runs.",
        "",
        "| Reviewed | Model | Task class | Difficulty | Verdict | Score /5 | First-pass | Safe final state |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for record in sorted(records, key=record_time, reverse=True)[:DISPLAY_LIMIT]:
        safe = record.get("safe_final_state_verified")
        safe_text = "Verified" if safe is True else "Not controller-verified" if safe is False else "Not applicable"
        row = (
            format_time(record),
            record["model"],
            title_case(record["task_class"]),
            title_case(record["difficulty"]),
            str(record["outcome"]).upper(),
            f"{float(record['weighted_score_5']):.2f}",
            "Yes" if record["first_pass_accepted"] else "No",
            safe_text,
        )
        lines.append("| " + " | ".join(markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)

def detailed_runs(records: list[dict[str, Any]]) -> str:
    lines = [
        "## Latest formal evaluations",
        "",
        f"Newest first. This section displays at most {DISPLAY_LIMIT} formal evaluation runs.",
    ]
    for record in sorted(records, key=record_time, reverse=True)[:DISPLAY_LIMIT]:
        safe = record.get("safe_final_state_verified")
        safe_text = "Verified" if safe is True else "Not controller-verified" if safe is False else "Not applicable"
        lines.extend(
            [
                "",
                f"### {record['model']} - {title_case(record['task_class'])}",
                "",
                f"- Reviewed: **{format_time(record)}**",
                f"- Run ID: `{record['run_id']}`",
                f"- Subject alias: `{record['subject_alias']}`",
                f"- Result: **{str(record['outcome']).upper()}**",
                f"- Weighted score: **{float(record['weighted_score_5']):.2f}/5**",
                f"- First-pass accepted: **{'Yes' if record['first_pass_accepted'] else 'No'}**",
                f"- Safe final state: **{safe_text}**",
                "- Principal strengths:",
            ]
        )
        strengths = record.get("verified_strengths") or ["none recorded"]
        lines.extend(f"  - {item}" for item in strengths)
        lines.append("- Principal defects:")
        defects = record.get("verified_defects") or ["none recorded"]
        lines.extend(f"  - {item}" for item in defects)
    return "\n".join(lines)

def render_readme_block(evaluations: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    recommendation_str = render_recommendation_section(manifest)
    return "\n".join(
        [
            recommendation_str,
            "",
            "## Summary model scores",
            "",
            "This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).",
            "",
            summary_table(evaluations, include_flags=False),
            "",
            task_table(evaluations, heading="Task-class scorecard"),
            "",
            "These tables are generated from the append-only ledger. Do not edit them manually.",
        ]
    )

def render_scorecard_block(evaluations: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        [
            "## Summary score table\n\n" + summary_table(evaluations, include_flags=True),
            formal_runs_table(evaluations),
            task_table(evaluations, heading="Task-class aggregates"),
            detailed_runs(evaluations),
        ]
    )

def replace_generated_block(text: str, start: str, end: str, replacement: str) -> str:
    wrapped = f"{start}\n{replacement.rstrip()}\n{end}"
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1:
            fail(f"generated markers are missing or duplicated: {start}")
        before, remainder = text.split(start, 1)
        _, after = remainder.split(end, 1)
        return before + wrapped + after

    fallback_start = "## AI Model Recommendations & Operational Guidance" if "README" in start else "## Summary score table"
    if fallback_start not in text:
        fallback_start = "## Summary model scores"
    if fallback_start not in text:
        fail(f"cannot locate initial generated section for {start}")
    before, after = text.split(fallback_start, 1)
    return before + wrapped + "\n\n" + fallback_start + after

def scorecard_updated_line(records: list[dict[str, Any]]) -> str:
    if not records:
        return "Updated: 29 July 2026, 10:00 SGT"
    value = max(record_time(record) for record in records)
    suffix = " SGT" if value.utcoffset() == timedelta(hours=8) else ""
    return f"Updated: {value.day} {value.strftime('%B %Y, %H:%M')}{suffix}"

def expected_files(evaluations: list[dict[str, Any]], total_queued_count: int = 0) -> tuple[str, str, dict[str, Any]]:
    readme = README_PATH.read_text(encoding="utf-8")
    scorecard = SCORECARD_PATH.read_text(encoding="utf-8")
    if not readme.startswith(README_TITLE + "\n"):
        fail(f"README.md must begin with exactly: {README_TITLE}")
    if not scorecard.startswith(SCORECARD_TITLE + "\n"):
        fail(f"scorecard.md must begin with exactly: {SCORECARD_TITLE}")

    manifest = generate_recommendation_manifest(evaluations, total_queued_count=total_queued_count)

    expected_readme = replace_generated_block(
        readme,
        README_START,
        README_END,
        render_readme_block(evaluations, manifest),
    )
    expected_scorecard = replace_generated_block(
        scorecard,
        SCORECARD_START,
        SCORECARD_END,
        render_scorecard_block(evaluations),
    )
    expected_scorecard, update_count = re.subn(
        r"(?m)^Updated: .+$",
        scorecard_updated_line(evaluations),
        expected_scorecard,
        count=1,
    )
    if update_count != 1:
        fail("scorecard must contain exactly one top-level Updated line")
    return expected_readme, expected_scorecard, manifest

def rebuild_views(total_queued_count: int = 0) -> None:
    records = load_records()
    evaluations = resolved_evaluations(records)
    expected_readme, expected_scorecard, manifest = expected_files(evaluations, total_queued_count=total_queued_count)

    RECOMMENDATION_JSON_PATH.parent.mkdir(exist_ok=True)
    with open(RECOMMENDATION_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    README_PATH.write_text(expected_readme, encoding="utf-8", newline="\n")
    SCORECARD_PATH.write_text(expected_scorecard, encoding="utf-8", newline="\n")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify generated views without writing")
    args = parser.parse_args()

    try:
        records = load_records()
        evaluations = resolved_evaluations(records)
        expected_readme, expected_scorecard, manifest = expected_files(evaluations)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Ledger view generation failed: {exc}", file=sys.stderr)
        return 1

    mismatches: list[str] = []
    if README_PATH.read_text(encoding="utf-8") != expected_readme:
        mismatches.append("README.md")
    if SCORECARD_PATH.read_text(encoding="utf-8") != expected_scorecard:
        mismatches.append("scorecard.md")

    if args.check:
        if mismatches:
            print("Generated ledger views are stale: " + ", ".join(mismatches), file=sys.stderr)
            print("Run: python scripts/rebuild_views.py", file=sys.stderr)
            return 1
        print(f"Ledger views passed: complete history retained; newest {DISPLAY_LIMIT} runs displayed.")
        return 0

    rebuild_views()
    print("Updated README.md, scorecard.md, and analysis/model-recommendation.json.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
