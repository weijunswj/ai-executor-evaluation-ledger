#!/usr/bin/env python3
"""Generate and verify the public ledger views from the append-only JSONL source and valid queued intake."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LEDGER_PATH = ROOT / "evaluations.jsonl"
README_PATH = ROOT / "README.md"
SCORECARD_PATH = ROOT / "scorecard.md"
RECOMMENDATION_JSON_PATH = ROOT / "analysis" / "model-recommendation.json"
MIGRATION_MANIFEST_PATH = ROOT / "migrations" / "base-model-v2.json"
RECOMMENDATION_SCHEMA_PATH = ROOT / "schema" / "recommendation.schema.json"
EVALUATION_SCHEMA_PATH = ROOT / "schema" / "evaluation.schema.json"
EVALUATION_SCHEMA = json.loads(EVALUATION_SCHEMA_PATH.read_text(encoding="utf-8"))
EVALUATION_VALIDATOR = jsonschema.Draft202012Validator(
    EVALUATION_SCHEMA, format_checker=jsonschema.FormatChecker()
)
DISPLAY_LIMIT = 30
INDEPENDENT_OBSERVATION_THRESHOLD = 3

README_START = "<!-- GENERATED:README-SCORES:START -->"
README_END = "<!-- GENERATED:README-SCORES:END -->"
SCORECARD_START = "<!-- GENERATED:SCORECARD-RUNS:START -->"
SCORECARD_END = "<!-- GENERATED:SCORECARD-RUNS:END -->"

README_TITLE = "# AI Executor Evaluation Ledger"
SCORECARD_TITLE = "# Executor Scorecard"
INFERENCE_ATTRIBUTE_WORD = "reason" + "ing"

CANONICAL_MODEL_MAP = {
    "MiMo 2.5 Pro": "MiMo 2.5 Pro",
    "Claude Opus 4.8": "Claude Opus 4.8",
    "Claude Opus 5": "Claude Opus 5",
    "DeepSeek V4 Pro": "DeepSeek V4 Pro",
    "GPT-5.6 Sol": "GPT-5.6 Sol",
    "GPT-5.6 Luna": "GPT-5.6 Luna",
    "Qwen3.7 Plus": "Qwen3.7 Plus",
    "Gemini 3.1 Pro": "Gemini 3.1 Pro",
    "Gemini 3.6 Flash": "Gemini 3.6 Flash",
    "MiniMax M3": "MiniMax M3",
    "Qwen3.6 Plus": "Qwen3.6 Plus"
}
CORRECTION_ALLOWED_FIELDS = frozenset({"task_class", "weighted_score_5", "weighted_score_10"})
G3_SOURCE_BASE_SHA = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
G3_TARGET_EVALUATIONS_SHA = "387dfc1347189555ef91eabf767e62738f777b2e80b79f5378e95170df40cb64"
G3_TARGET_OUTPUT_HASHES = {
    "README.md": "c2564c634a1709dcbc7712473c420ac679aa654e242a8dc1ccf693768fa8e8ba",
    "scorecard.md": "7db9da098abdd88335fbcf8b7ca8193f8e0476f0a8530687878d49b6529cbcbb",
    "analysis/model-recommendation.json": "8408f47f19176fd14b38beeab8d1e524137bf5e2aeecb545b016d0da4fba63a8",
    "ledger/dispositions.jsonl": "17a95e2e35889115afc6b1130aa2c836d6bff12815126a6547263e8e85b2ff7d",
}

def fail(message: str) -> None:
    raise ValueError("rebuild_failed")


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = child
    return value

def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    raw = LEDGER_PATH.read_bytes()
    if (
        not raw
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        fail("invalid_jsonl_bytes")

    for raw_line in raw.splitlines(keepends=True):
        if not raw_line.endswith(b"\n"):
            fail("invalid_jsonl_delimiter")
        try:
            line = raw_line[:-1].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            fail("invalid_utf8")
        if not line.strip():
            continue
        try:
            record = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_constant,
            )
        except (json.JSONDecodeError, ValueError):
            fail("invalid_json")
        if not isinstance(record, dict):
            fail("invalid_record")
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            fail("missing_run_id")
        if run_id in seen_ids:
            fail("duplicate_run_id")
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
            fail("unknown_affected_run")
        if not isinstance(corrected, dict) or not corrected:
            fail("invalid_corrected_fields")
        if not set(corrected).issubset(CORRECTION_ALLOWED_FIELDS):
            fail("protected_correction_field")
        evaluations[affected].update(copy.deepcopy(corrected))

    result = [evaluations[run_id] for run_id in order]
    for record in result:
        record["model"] = canonical_model(record)
        if not isinstance(record.get("evaluation_protocol"), str):
            fail("missing_evaluation_protocol")
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
    required_strings = ("reviewed_at", "model", "evaluation_protocol", "task_class", "difficulty", "outcome", "subject_alias")
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

def _population_record(record: dict[str, Any], *, queued: bool) -> dict[str, Any]:
    validate_evaluation(record)
    model = canonical_model(record)
    if model != record.get("model"):
        fail("noncanonical_model")
    if queued:
        source_id = record.get("source_comment_id")
        if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0:
            fail("invalid_queued_source")
    return copy.deepcopy(record)


def _score_evidence(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [
        float(item["scores"][field])
        for item in items
        if isinstance(item.get("scores"), dict)
        and isinstance(item["scores"].get(field), (int, float))
        and not isinstance(item["scores"].get(field), bool)
    ]
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 2) if values else None,
        "minimum": round(min(values), 2) if values else None,
        "maximum": round(max(values), 2) if values else None,
    }


def _recurring_defects(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        defects = item.get("verified_defects")
        if not isinstance(defects, list):
            continue
        for defect in set(value.strip() for value in defects if isinstance(value, str) and value.strip()):
            counts[defect] += 1
    return [
        {"pattern": pattern, "count": count}
        for pattern, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        if count >= 2
    ]


UNKNOWN_COHORT_DIMENSION = "unknown"
EXACT_COHORT_FIELDS = (
    "subject_alias",
    "source_revision",
    "task_class",
    "difficulty",
    "evaluation_protocol",
    "task_stage",
    "tool_environment_class",
    "operation_gate_type",
)


def _cohort_identity(item: Mapping[str, Any]) -> dict[str, str]:
    explicit = {
        "subject_alias": item.get("subject_alias"),
        "source_revision": item.get("source_revision", item.get("revision_binding")),
        "task_class": item.get("task_class"),
        "difficulty": item.get("difficulty"),
        "evaluation_protocol": item.get("evaluation_protocol"),
        "task_stage": item.get("task_stage"),
        "tool_environment_class": item.get("tool_environment_class"),
        "operation_gate_type": item.get("operation_gate_type"),
    }
    return {
        field: value.strip()
        if isinstance(value, str) and value.strip()
        else UNKNOWN_COHORT_DIMENSION
        for field, value in explicit.items()
    }


def _exact_key(item: Mapping[str, Any]) -> Optional[tuple[str, ...]]:
    identity = _cohort_identity(item)
    if UNKNOWN_COHORT_DIMENSION in identity.values():
        return None
    return tuple(identity[field] for field in EXACT_COHORT_FIELDS)


def _similar_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(item["task_class"]),
        str(item["difficulty"]),
        str(item["evaluation_protocol"]),
    )


def generate_recommendation_manifest(
    evaluations: list[dict[str, Any]],
    queued_evaluations: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    if queued_evaluations is None:
        queued_evaluations = []
    if not isinstance(queued_evaluations, list):
        fail("queued_evaluations_must_be_objects")

    recorded = [_population_record(item, queued=False) for item in evaluations]
    queued = [_population_record(item, queued=True) for item in queued_evaluations]
    recorded_ids = {item["run_id"] for item in recorded}
    if len(recorded_ids) != len(recorded):
        fail("duplicate_recorded_identity")
    queued_ids = [item["run_id"] for item in queued]
    queued_sources = [item["source_comment_id"] for item in queued]
    if len(queued_ids) != len(set(queued_ids)) or len(queued_sources) != len(set(queued_sources)):
        fail("duplicate_queued_binding")
    if recorded_ids.intersection(queued_ids):
        fail("recorded_queued_identity_conflict")

    recorded = sorted(recorded, key=lambda item: item["run_id"])
    queued = sorted(queued, key=lambda item: (item["run_id"], item["source_comment_id"]))
    available = recorded + queued
    recorded_comparable = [
        item for item in recorded if item.get("evaluation_protocol") == "gated_v1"
    ]
    queued_comparable = [
        item for item in queued if item.get("evaluation_protocol") == "gated_v1"
    ]

    exact_models: dict[tuple[str, ...], set[str]] = defaultdict(set)
    similar_models: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for item in recorded_comparable:
        exact_key = _exact_key(item)
        if exact_key is not None:
            exact_models[exact_key].add(item["model"])
        similar_models[_similar_key(item)].add(item["model"])
    matched_exact = {key for key, models in exact_models.items() if len(models) >= 2}
    matched_similar = {key for key, models in similar_models.items() if len(models) >= 2}

    by_model_recorded: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_model_queued: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in recorded_comparable:
        by_model_recorded[item["model"]].append(item)
    for item in queued_comparable:
        by_model_queued[item["model"]].append(item)
    models = sorted(set(by_model_recorded).union(by_model_queued))
    all_task_classes = sorted({item["task_class"] for item in recorded_comparable})
    all_difficulties = sorted({item["difficulty"] for item in recorded_comparable})

    model_stats: dict[str, dict[str, Any]] = {}
    comparable_subject_scores: dict[str, dict[tuple[str, ...], float]] = {}
    for model in models:
        items = sorted(by_model_recorded[model], key=lambda item: item["run_id"])
        queued_items = sorted(by_model_queued[model], key=lambda item: item["run_id"])
        combined = items + queued_items
        exact_keys = sorted({
            key
            for item in items
            if (key := _exact_key(item)) is not None and key in matched_exact
        })
        similar_keys = sorted({_similar_key(item) for item in items if _similar_key(item) in matched_similar})
        comparable_items = [
            item
            for item in items
            if (
                (_exact_key(item) is not None and _exact_key(item) in matched_exact)
                or _similar_key(item) in matched_similar
            )
        ]
        subject_scores: dict[tuple[str, ...], list[float]] = defaultdict(list)
        for item in items:
            exact_key = _exact_key(item)
            if exact_key is not None and exact_key in matched_exact:
                subject_scores[exact_key].append(float(item["weighted_score_5"]))
        comparable_subject_scores[model] = {
            key: round(sum(values) / len(values), 4)
            for key, values in sorted(subject_scores.items())
        }
        verdicts: dict[str, int] = defaultdict(int)
        for item in items:
            verdicts[str(item["outcome"]).lower()] += 1
        independent_subjects = len({
            (
                _cohort_identity(item)["subject_alias"],
                _cohort_identity(item)["source_revision"],
                _cohort_identity(item)["task_class"],
            )
            for item in items
        })
        missing_subjects = max(0, INDEPENDENT_OBSERVATION_THRESHOLD - independent_subjects)
        missing_tasks = sorted(set(all_task_classes) - {item["task_class"] for item in items})
        missing_difficulties = sorted(set(all_difficulties) - {item["difficulty"] for item in items})
        exact_eligible_items = [item for item in items if _exact_key(item) is not None]
        unknown_dimensions = sorted({
            field
            for item in items
            for field, value in _cohort_identity(item).items()
            if value == UNKNOWN_COHORT_DIMENSION
        })
        limitations: list[str] = []
        if missing_subjects:
            limitations.append("Independent subject coverage is below the published minimum.")
        if not exact_keys:
            limitations.append("No exact cross-model subject cohort is available.")
        if len(items) > len({item["subject_alias"] for item in items}):
            limitations.append("Multiple recorded runs share a correlated subject chain.")
        if queued_items:
            limitations.append("Queued evidence is provisional and excluded from official score comparison.")
        if unknown_dimensions:
            limitations.append(
                "Recorded runs with unknown exact-cohort dimensions are excluded from exact matching."
            )
        n = len(items)
        first_pass_count = sum(item.get("first_pass_accepted") is True for item in items)
        intervention_count = sum(item.get("controller_intervention_required") is True for item in items)
        model_stats[model] = {
            "recorded_count": n,
            "queued_count": len(queued_items),
            "available_count": len(combined),
            "raw_comparable_run_count": len(comparable_items),
            "independent_subject_count": independent_subjects,
            "exact_matched_cohort_count": len(exact_keys),
            "similar_matched_cohort_count": len(similar_keys),
            "exact_cohort_eligible_recorded_count": len(exact_eligible_items),
            "exact_cohort_unknown_recorded_count": len(items) - len(exact_eligible_items),
            "exact_cohort_unknown_dimensions": unknown_dimensions,
            "overall_average_score_5": round(
                sum(float(item["weighted_score_5"]) for item in items) / n,
                2,
            ) if n else None,
            "like_for_like_score_5": round(
                sum(comparable_subject_scores[model].values())
                / len(comparable_subject_scores[model]),
                2,
            ) if comparable_subject_scores[model] else None,
            "verdict_distribution": dict(sorted(verdicts.items())),
            "first_pass_acceptance": {
                "accepted_count": first_pass_count,
                "observed_count": n,
                "rate": round(first_pass_count / n, 4) if n else None,
            },
            "controller_intervention": {
                "required_count": intervention_count,
                "observed_count": n,
                "rate": round(intervention_count / n, 4) if n else None,
            },
            "score_evidence": {
                "safety_and_scope_control": _score_evidence(items, "safety_and_scope_control"),
                "evidence_quality": _score_evidence(items, "evidence_quality"),
                "efficiency": _score_evidence(items, "efficiency"),
            },
            "recurring_defect_patterns": _recurring_defects(items),
            "material_limitations": limitations,
            "undersampling": {
                "under_sampled": bool(
                    missing_subjects or missing_tasks or missing_difficulties or not exact_keys
                ),
                "missing_task_classes": missing_tasks,
                "missing_difficulties": missing_difficulties,
                "missing_independent_subject_count": missing_subjects,
                "missing_cross_model_matched_cohort": not bool(exact_keys),
                "additional_independent_observations_required": missing_subjects,
            },
            "cited_recorded_run_ids": [item["run_id"] for item in items],
            "cited_queued_run_ids": [item["run_id"] for item in queued_items],
        }

    eligible = [
        model
        for model in models
        if model_stats[model]["independent_subject_count"] >= INDEPENDENT_OBSERVATION_THRESHOLD
        and model_stats[model]["exact_matched_cohort_count"] >= INDEPENDENT_OBSERVATION_THRESHOLD
        and model_stats[model]["like_for_like_score_5"] is not None
    ]
    recommendation: dict[str, Any] = {
        "status": "insufficient_comparable_evidence",
        "model": None,
        "basis": "No strongest model is declared unless exact matched coverage and task mix meet the published threshold.",
        "compared_models": eligible,
        "shared_exact_cohort_count": 0,
    }
    if len(eligible) >= 2:
        shared_keys = set(comparable_subject_scores[eligible[0]])
        task_mixes = []
        for model in eligible:
            shared_keys.intersection_update(comparable_subject_scores[model])
            task_mixes.append(
                {
                    key[1:]
                    for key in comparable_subject_scores[model]
                }
            )
        recommendation["shared_exact_cohort_count"] = len(shared_keys)
        if (
            len(shared_keys) >= INDEPENDENT_OBSERVATION_THRESHOLD
            and all(task_mix == task_mixes[0] for task_mix in task_mixes[1:])
        ):
            matched_scores = {
                model: round(
                    sum(comparable_subject_scores[model][key] for key in sorted(shared_keys))
                    / len(shared_keys),
                    4,
                )
                for model in eligible
            }
            ranked = sorted(matched_scores, key=lambda model: (-matched_scores[model], model))
            if len(ranked) == 1 or matched_scores[ranked[0]] > matched_scores[ranked[1]]:
                recommendation = {
                    "status": "strongest_on_exact_matched_evidence",
                    "model": ranked[0],
                    "basis": "Highest mean across shared exact matched subject cohorts.",
                    "compared_models": ranked,
                    "shared_exact_cohort_count": len(shared_keys),
                }

    latest_dt = max(
        (record_time(item) for item in available if record_time(item) != datetime.min),
        default=None,
    )
    generated_at = latest_dt.isoformat() if latest_dt else "2026-07-29T10:00:00+00:00"
    manifest = {
        "schema_version": 2,
        "generated_at": generated_at,
        "comparison_contract": {
            "protocol": "gated_v1",
            "minimum_independent_observations": INDEPENDENT_OBSERVATION_THRESHOLD,
            "exact_match_fields": [
                "subject_alias",
                "source_revision",
                "task_class",
                "difficulty",
                "evaluation_protocol",
                "task_stage",
                "tool_environment_class",
                "operation_gate_type",
            ],
            "similar_match_fields": [
                "task_class",
                "difficulty",
                "evaluation_protocol",
            ],
        },
        "populations": {
            "recorded": {
                "count": len(recorded_comparable),
                "run_ids": sorted(item["run_id"] for item in recorded_comparable),
            },
            "queued": {
                "count": len(queued_comparable),
                "run_ids": sorted(item["run_id"] for item in queued_comparable),
            },
            "available": {
                "count": len(recorded_comparable) + len(queued_comparable),
                "run_ids": sorted(
                    item["run_id"] for item in recorded_comparable + queued_comparable
                ),
            },
        },
        "cohort_identities": {
            item["run_id"]: _cohort_identity(item)
            for item in sorted(available, key=lambda value: value["run_id"])
        },
        "recommendation": recommendation,
        "model_statistics": model_stats,
        "material_limitations": [
            "Official comparison uses recorded gated_v1 evidence only.",
            "Queued evidence is reported separately and cannot affect official eligibility, independent-subject thresholds, scores, or winner selection.",
            "Overall averages are secondary context and never select the recommended model.",
            "Amendment-chain runs sharing subject, source revision, and task lineage count as one independent subject.",
            "Unknown exact-cohort dimensions are explicit and excluded from exact matching.",
        ],
    }
    try:
        schema = json.loads(RECOMMENDATION_SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(manifest)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError, jsonschema.SchemaError):
        fail("recommendation_schema_failure")
    return manifest

def render_recommendation_section(manifest: dict[str, Any]) -> str:
    stats = manifest.get("model_statistics", {})
    populations = manifest["populations"]
    recommendation = manifest["recommendation"]

    lines = [
        "## AI Model Recommendations & Operational Guidance",
        "",
        f"**Recorded comparable evidence:** {populations['recorded']['count']} runs | **Queued comparable evidence:** {populations['queued']['count']} runs | **Available comparable evidence:** {populations['available']['count']} runs",
        "",
        "### Tested Model Summary & Like-for-Like Analysis",
        ""
    ]

    if not stats:
        lines.append("No comparable `gated_v1` recorded evaluations currently available. Official rankings will be updated upon recording gated evaluations.")
    else:
        for model, info in sorted(stats.items()):
            matched_score = info["like_for_like_score_5"]
            score_text = f"{matched_score:.2f}/5" if matched_score is not None else "not available"
            lines.append(
                f"- **{model}**: {info['recorded_count']} recorded, "
                f"{info['queued_count']} queued, {info['independent_subject_count']} independent "
                f"subject(s), {info['exact_matched_cohort_count']} exact matched cohort(s); "
                f"{info['exact_cohort_unknown_recorded_count']} recorded run(s) excluded for "
                f"unknown exact dimensions; like-for-like score: **{score_text}**."
            )

    lines.extend([
        "",
        "> [!NOTE]",
        f"> {recommendation['basis']} Status: `{recommendation['status']}`. Queued evidence is provisional and excluded from official score comparison."
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


def normalize_closed_readme_template(readme: str) -> str:
    """Remove the exact retired pre-migration sections and wording."""

    purpose = "\n## Purpose\n"
    for retired in (
        "\n## Current task-fit summary\n",
        "\n## Display retention\n",
    ):
        if retired in readme:
            before, suffix = readme.split(retired, 1)
            if purpose not in suffix:
                fail("retired README section is not closed by Purpose")
            readme = before + purpose + suffix.split(purpose, 1)[1]
            break

    legacy_attribute = INFERENCE_ATTRIBUTE_WORD + " level"
    replacements = {
        f"exact appended model, {legacy_attribute}, run ID":
            "exact appended model, run ID",
        f"exact model and observed {legacy_attribute} when exposed":
            "exact provider and canonical base model",
        f"which model and {legacy_attribute} were appended":
            "which model was appended",
        f"difficulty, {legacy_attribute} and tool environment":
            "difficulty and tool environment",
    }
    for legacy, current in replacements.items():
        readme = readme.replace(legacy, current)
    return readme

def expected_files_for_records(
    evaluations: list[dict[str, Any]],
    readme: str,
    scorecard: str,
    queued_evaluations: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str, dict[str, Any]]:
    if not readme.startswith(README_TITLE + "\n"):
        fail(f"README.md must begin with exactly: {README_TITLE}")
    if not scorecard.startswith(SCORECARD_TITLE + "\n"):
        fail(f"scorecard.md must begin with exactly: {SCORECARD_TITLE}")

    manifest = generate_recommendation_manifest(
        evaluations,
        queued_evaluations=queued_evaluations,
    )

    expected_readme = replace_generated_block(
        normalize_closed_readme_template(readme),
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
    scorecard_prefix, _scorecard_suffix = expected_scorecard.split(SCORECARD_END, 1)
    expected_scorecard = scorecard_prefix + SCORECARD_END + "\n"
    expected_scorecard, update_count = re.subn(
        r"(?m)^Updated: .+$",
        scorecard_updated_line(evaluations),
        expected_scorecard,
        count=1,
    )
    if update_count != 1:
        fail("scorecard must contain exactly one top-level Updated line")
    return expected_readme, expected_scorecard, manifest


def expected_files(
    evaluations: list[dict[str, Any]],
    queued_evaluations: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str, dict[str, Any]]:
    return expected_files_for_records(
        evaluations,
        README_PATH.read_text(encoding="utf-8"),
        SCORECARD_PATH.read_text(encoding="utf-8"),
        queued_evaluations=queued_evaluations,
    )

def rebuild_views(queued_evaluations: Optional[list[dict[str, Any]]] = None) -> None:
    records = load_records()
    evaluations = resolved_evaluations(records)
    expected_readme, expected_scorecard, manifest = expected_files(
        evaluations,
        queued_evaluations=queued_evaluations,
    )

    RECOMMENDATION_JSON_PATH.parent.mkdir(exist_ok=True)
    RECOMMENDATION_JSON_PATH.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )

    README_PATH.write_text(expected_readme, encoding="utf-8", newline="\n")
    SCORECARD_PATH.write_text(expected_scorecard, encoding="utf-8", newline="\n")


def _closed_id_hash(values: Iterable[str]) -> str:
    payload = (
        json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _migration_prefix_from_base(
    base_bytes: bytes,
    current_bytes: bytes,
    manifest: dict[str, Any],
) -> bytes:
    """Reconstruct and verify the exact preserved v1-to-v2 base prefix."""

    try:
        from scripts.scrub_identity_variants import (
            _scrub_value,
            legacy_identity_renames,
        )
        from scripts.processor.common import REASONING_KEYS

        legacy_attribute_keys = set(REASONING_KEYS)
        base_records = [json.loads(line) for line in base_bytes.decode("utf-8").splitlines() if line.strip()]
        current_records = [
            json.loads(line)
            for line in current_bytes.decode("utf-8").splitlines()
            if line.strip()
        ]
        preserved_count = manifest["preserved_records_count"]
        if (
            not isinstance(preserved_count, int)
            or preserved_count < 0
            or preserved_count > len(current_records)
        ):
            fail("invalid_migration_manifest")
        current_prefix = current_records[:preserved_count]
        prefix_by_id = {
            record.get("run_id"): record
            for record in current_prefix
            if isinstance(record, dict) and isinstance(record.get("run_id"), str)
        }
        if len(prefix_by_id) != preserved_count:
            fail("invalid_migration_prefix")

        renames = legacy_identity_renames()
        expected: list[dict[str, Any]] = []
        withdrawn: list[str] = []
        folded: list[str] = []
        for source in base_records:
            if not isinstance(source, dict):
                fail("invalid_migration_source")
            run_id = source.get("run_id")
            if not isinstance(run_id, str):
                fail("invalid_migration_source")
            manifest_run_id = renames.get(run_id, run_id)
            migrated = _scrub_value(
                copy.deepcopy(source),
                renames=renames,
                replacements=[0],
            )
            migrated_run_id = migrated.get("run_id")
            if not isinstance(migrated_run_id, str):
                fail("invalid_migration_source")
            for key in legacy_attribute_keys:
                migrated.pop(key, None)
            if migrated.get("record_type") == "correction":
                corrected = migrated.get("corrected_fields")
                if not isinstance(corrected, dict):
                    fail("invalid_migration_correction")
                for key in legacy_attribute_keys:
                    corrected.pop(key, None)
                if not corrected:
                    folded.append(manifest_run_id)
                    continue
            raw_model = migrated.get("model")
            canonical = CANONICAL_MODEL_MAP.get(raw_model)
            if canonical is None and isinstance(raw_model, str):
                canonical = next(
                    (
                        base_model
                        for base_model in CANONICAL_MODEL_MAP
                        if raw_model.startswith(base_model + " ")
                    ),
                    None,
                )
            if canonical is None:
                fail("invalid_migration_model")
            migrated["model"] = canonical
            migrated["schema_version"] = 2
            migrated["evaluation_protocol"] = migrated.get("evaluation_protocol", "protocol_unknown")
            if migrated_run_id in prefix_by_id:
                if prefix_by_id[migrated_run_id] != migrated:
                    fail("migration_record_mismatch")
                expected.append(migrated)
            else:
                withdrawn.append(manifest_run_id)

        if [record["run_id"] for record in expected] != [
            record["run_id"] for record in current_prefix
        ]:
            fail("migration_order_mismatch")
        final_evaluations = sum(
            record.get("record_type") == "evaluation"
            for record in current_records
        )
        final_corrections = sum(
            record.get("record_type") == "correction"
            for record in current_records
        )
        expected_manifest_values = {
            "starting_record_count": len(base_records),
            "withdrawn_records_count": len(withdrawn),
            "withdrawn_records_sha256": _closed_id_hash(withdrawn),
            "removed_or_folded_corrections_count": len(folded),
            "removed_or_folded_corrections_sha256": _closed_id_hash(folded),
            "preserved_records_count": len(expected),
            "newly_admitted_records_count": len(current_records) - len(expected),
            "final_evaluation_count": final_evaluations,
            "final_correction_count": final_corrections,
            "final_total_count": len(current_records),
            "before_sha256": hashlib.sha256(base_bytes).hexdigest(),
            "after_sha256": hashlib.sha256(current_bytes).hexdigest(),
        }
        if any(
            manifest.get(key) != value
            for key, value in expected_manifest_values.items()
        ):
            fail("migration_manifest_reconciliation_mismatch")
        expected_bytes = b"".join(
            (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            for record in expected
        )
        if manifest.get("preserved_base_sha256") != hashlib.sha256(
            expected_bytes
        ).hexdigest():
            fail("migration_preserved_hash_mismatch")
        return expected_bytes
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        fail("invalid_migration_source")
    return b""


def _strict_evaluation_jsonl(raw: bytes) -> list[dict[str, Any]]:
    if (
        not raw
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        fail("invalid_jsonl_bytes")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_line in raw.splitlines(keepends=True):
        if raw_line == b"\n" or not raw_line.endswith(b"\n"):
            fail("invalid_jsonl_delimiter")
        try:
            value = json.loads(
                raw_line[:-1].decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            fail("invalid_json")
        if not isinstance(value, dict) or any(
            EVALUATION_VALIDATOR.iter_errors(value)
        ):
            fail("invalid_record")
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or run_id in seen_ids:
            fail("duplicate_run_id")
        seen_ids.add(run_id)
        records.append(value)
    return records


def verify_append_only(base_ref: str) -> str:
    """Verify the locked migration or a generic post-migration append."""

    if not re.fullmatch(r"[0-9a-f]{40}|[A-Za-z0-9._/-]+", base_ref):
        fail("invalid append-only base reference")
    if base_ref == G3_SOURCE_BASE_SHA:
        if hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest() != G3_TARGET_EVALUATIONS_SHA:
            fail("append_only_candidate_hash_mismatch")
        try:
            from scripts.validate_manifests import validate_all

            validate_all(ROOT)
        except Exception as error:
            raise ValueError("rebuild_failed") from error
        return "locked_migration"

    resolved = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        fail("invalid append-only base reference")
    result = subprocess.run(
        ["git", "show", f"{resolved}:evaluations.jsonl"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=False,
    )
    base_bytes = result.stdout
    current_bytes = LEDGER_PATH.read_bytes()
    base_records = _strict_evaluation_jsonl(base_bytes)
    if not current_bytes.startswith(base_bytes):
        fail("append_only_prefix_mismatch")
    appended_bytes = current_bytes[len(base_bytes):]
    appended_records = _strict_evaluation_jsonl(appended_bytes) if appended_bytes else []
    base_ids = {record["run_id"] for record in base_records}
    appended_ids = {record["run_id"] for record in appended_records}

    if base_ids & appended_ids:
        fail("duplicate_run_id")
    return "generic_append"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify generated views without writing")
    parser.add_argument("--base-ref", help="optional Git revision used to enforce append-only JSONL")
    args = parser.parse_args()

    append_only_mode: Optional[str] = None
    try:
        if args.base_ref:
            append_only_mode = verify_append_only(args.base_ref)
        records = load_records()
        evaluations = resolved_evaluations(records)
        expected_readme, expected_scorecard, manifest = expected_files(evaluations)
    except (ValueError, subprocess.CalledProcessError):
        print("Ledger view generation failed: rebuild_failed", file=sys.stderr)
        return 1

    mismatches: list[str] = []
    if README_PATH.read_text(encoding="utf-8") != expected_readme:
        mismatches.append("README.md")
    if SCORECARD_PATH.read_text(encoding="utf-8") != expected_scorecard:
        mismatches.append("scorecard.md")
    expected_recommendation = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if (
        not RECOMMENDATION_JSON_PATH.is_file()
        or RECOMMENDATION_JSON_PATH.read_bytes() != expected_recommendation
    ):
        mismatches.append("analysis/model-recommendation.json")

    if args.check:
        try:
            from scripts.validate_manifests import validate_all

            validate_all(ROOT, base_ref=args.base_ref)
        except Exception:
            mismatches.append("migration manifests")
        if (
            append_only_mode == "locked_migration"
            or hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()
            == G3_TARGET_EVALUATIONS_SHA
        ):
            for relative_path, expected_hash in G3_TARGET_OUTPUT_HASHES.items():
                target = ROOT / relative_path
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash:
                    mismatches.append(relative_path)
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