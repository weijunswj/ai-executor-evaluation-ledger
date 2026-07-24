#!/usr/bin/env python3
"""Generate and verify the public ledger views from the append-only JSONL source."""

from __future__ import annotations

import argparse
import copy
import json
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
DISPLAY_LIMIT = 30

README_START = "<!-- GENERATED:README-SCORES:START -->"
README_END = "<!-- GENERATED:README-SCORES:END -->"
SCORECARD_START = "<!-- GENERATED:SCORECARD-RUNS:START -->"
SCORECARD_END = "<!-- GENERATED:SCORECARD-RUNS:END -->"

README_TITLE = "# AI Executor Evaluation Ledger"
SCORECARD_TITLE = "# Executor Scorecard"

MODEL_ALIASES = {
    "Sol Medium": "GPT-5.6 Sol Medium",
    "Sol High": "GPT-5.6 Sol High",
}

PLACEHOLDER_MODELS = (
    ("GPT-5.6 Sol Medium", "Medium"),
    ("GPT-5.6 Sol High", "High"),
)

MODEL_ORDER = (
    "Xiaomi MiMo 2.5 Pro",
    "Claude Opus 4.8 High",
    "GPT-5.6 Sol Medium",
    "GPT-5.6 Sol High",
)


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
        record["reasoning_display"] = reasoning_display(record)
        validate_evaluation(record)
    return result


def canonical_model(record: dict[str, Any]) -> str:
    model = str(record.get("model") or "").strip()
    observed = str(record.get("observed_reasoning_mode") or "").strip().lower()
    model = MODEL_ALIASES.get(model, model)
    if model == "GPT-5.6 Sol" and observed in {"medium", "high"}:
        model = f"GPT-5.6 Sol {observed.title()}"
    if not model:
        fail(f"{record.get('run_id')}: missing model")
    return model


def reasoning_display(record: dict[str, Any]) -> str:
    raw = record.get("observed_reasoning_mode")
    if raw is None or not str(raw).strip():
        return "Not exposed"
    value = str(raw).strip()
    lowered = value.lower().replace("_", "-")
    if lowered == "provider-default":
        return "Default"
    if lowered in {"low", "medium", "high", "max"}:
        return lowered.title()
    return value


def validate_evaluation(record: dict[str, Any]) -> None:
    run_id = record["run_id"]
    required_strings = ("reviewed_at", "model", "task_class", "difficulty", "outcome", "subject_alias")
    for field in required_strings:
        if not isinstance(record.get(field), str) or not record[field].strip():
            fail(f"{run_id}: missing {field}")
    try:
        datetime.fromisoformat(record["reviewed_at"])
    except ValueError as exc:
        fail(f"{run_id}: invalid reviewed_at: {exc}")
    score = record.get("weighted_score_5")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 5:
        fail(f"{run_id}: weighted_score_5 must be between 0 and 5")
    if not isinstance(record.get("first_pass_accepted"), bool):
        fail(f"{run_id}: first_pass_accepted must be boolean")
    for field in ("verified_strengths", "verified_defects", "integrity_and_control_flags"):
        if not isinstance(record.get(field), list):
            fail(f"{run_id}: {field} must be a list")


def record_time(record: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(record["reviewed_at"])


def format_time(record: dict[str, Any]) -> str:
    value = record_time(record)
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


def safe_state_summary(records: list[dict[str, Any]]) -> str:
    applicable = [record for record in records if record.get("safe_final_state_verified") is not None]
    if not applicable:
        return "-"
    verified = sum(record.get("safe_final_state_verified") is True for record in applicable)
    return f"{verified}/{len(applicable)} applicable"


def model_sort_key(item: tuple[str, str]) -> tuple[int, str, str]:
    model, reasoning = item
    try:
        rank = MODEL_ORDER.index(model)
    except ValueError:
        rank = len(MODEL_ORDER)
    return rank, model.lower(), reasoning.lower()


def group_models(records: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["model"], record["reasoning_display"])].append(record)
    for placeholder in PLACEHOLDER_MODELS:
        grouped.setdefault(placeholder, [])
    return grouped


def summary_table(records: list[dict[str, Any]], *, include_flags: bool) -> str:
    grouped = group_models(records)
    headers = [
        "Model",
        "Reasoning level",
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
        "|" + "|".join("---:" if index in {2, 3, 4, 5, 6} else "---" for index in range(len(headers))) + "|",
    ]

    for key in sorted(grouped, key=model_sort_key):
        model, reasoning = key
        model_records = grouped[key]
        run_count = len(model_records)
        if run_count:
            average = f"{sum(float(item['weighted_score_5']) for item in model_records) / run_count:.2f}"
            first_pass = percentage(sum(item["first_pass_accepted"] for item in model_records), run_count)
            safe_state = safe_state_summary(model_records)
            task_count = len({(item["task_class"], item["difficulty"]) for item in model_records})
            evidence = evidence_level(run_count, task_count)
            flags = str(sum(len(item["integrity_and_control_flags"]) for item in model_records))
        else:
            average = first_pass = safe_state = "-"
            evidence = evidence_level(0, 0)
            flags = "-"

        row: list[object] = [model, reasoning, run_count, average, first_pass, safe_state]
        if include_flags:
            row.append(flags)
        row.append(evidence)
        lines.append("| " + " | ".join(markdown_cell(item) for item in row) + " |")

    return "\n".join(lines)


def task_table(records: list[dict[str, Any]], *, heading: str) -> str:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record["model"], record["reasoning_display"], record["task_class"], record["difficulty"])
        grouped[key].append(record)

    lines = [
        f"## {heading}",
        "",
        "| Model | Reasoning level | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for key in sorted(grouped, key=lambda item: (*model_sort_key((item[0], item[1])), item[2], item[3])):
        model, reasoning, task_class, difficulty = key
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
                    reasoning,
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
        "| Reviewed | Model | Reasoning level | Task class | Difficulty | Verdict | Score /5 | First-pass | Safe final state |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]
    for record in sorted(records, key=record_time, reverse=True)[:DISPLAY_LIMIT]:
        safe = record.get("safe_final_state_verified")
        safe_text = "Verified" if safe is True else "Not controller-verified" if safe is False else "Not applicable"
        row = (
            format_time(record),
            record["model"],
            record["reasoning_display"],
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
                f"- Reasoning level: **{record['reasoning_display']}**",
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
        strengths = record["verified_strengths"] or ["none recorded"]
        lines.extend(f"  - {item}" for item in strengths)
        lines.append("- Principal defects:")
        defects = record["verified_defects"] or ["none recorded"]
        lines.extend(f"  - {item}" for item in defects)
    return "\n".join(lines)


def render_readme_block(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "## Summary model scores",
            "",
            "This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).",
            "",
            summary_table(records, include_flags=False),
            "",
            task_table(records, heading="Task-class scorecard"),
            "",
            "These tables are generated from the append-only ledger. Do not edit them manually.",
        ]
    )


def render_scorecard_block(records: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        [
            "## Summary score table\n\n" + summary_table(records, include_flags=True),
            formal_runs_table(records),
            task_table(records, heading="Task-class aggregates"),
            detailed_runs(records),
        ]
    )


def replace_generated_block(text: str, start: str, end: str, replacement: str, fallback_end_heading: str) -> str:
    wrapped = f"{start}\n{replacement.rstrip()}\n{end}"
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1:
            fail(f"generated markers are missing or duplicated: {start}")
        before, remainder = text.split(start, 1)
        _, after = remainder.split(end, 1)
        return before + wrapped + after

    fallback_start = "## Summary model scores" if "README" in start else "## Summary score table"
    if fallback_start not in text or fallback_end_heading not in text:
        fail(f"cannot locate initial generated section for {start}")
    before, remainder = text.split(fallback_start, 1)
    _, after = remainder.split(fallback_end_heading, 1)
    return before + wrapped + "\n\n" + fallback_end_heading + after


def expected_files(records: list[dict[str, Any]]) -> tuple[str, str]:
    readme = README_PATH.read_text(encoding="utf-8")
    scorecard = SCORECARD_PATH.read_text(encoding="utf-8")
    if not readme.startswith(README_TITLE + "\n"):
        fail(f"README.md must begin with exactly: {README_TITLE}")
    if not scorecard.startswith(SCORECARD_TITLE + "\n"):
        fail(f"scorecard.md must begin with exactly: {SCORECARD_TITLE}")

    expected_readme = replace_generated_block(
        readme,
        README_START,
        README_END,
        render_readme_block(records),
        "## Current task-fit summary",
    )
    expected_scorecard = replace_generated_block(
        scorecard,
        SCORECARD_START,
        SCORECARD_END,
        render_scorecard_block(records),
        "## Current interpretation",
    )
    return expected_readme, expected_scorecard


def check_append_only(base_ref: str | None) -> None:
    if not base_ref:
        return
    result = subprocess.run(
        ["git", "show", f"{base_ref}:evaluations.jsonl"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    base = result.stdout
    current = LEDGER_PATH.read_text(encoding="utf-8")
    if not current.startswith(base):
        fail("evaluations.jsonl is not append-only relative to the pull-request base")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify generated views without writing")
    parser.add_argument("--base-ref", help="optional Git revision used to enforce append-only JSONL")
    args = parser.parse_args()

    try:
        records = load_records()
        check_append_only(args.base_ref)
        evaluations = resolved_evaluations(records)
        expected_readme, expected_scorecard = expected_files(evaluations)
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

    README_PATH.write_text(expected_readme, encoding="utf-8", newline="\n")
    SCORECARD_PATH.write_text(expected_scorecard, encoding="utf-8", newline="\n")
    print("Updated README.md and scorecard.md from evaluations.jsonl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
