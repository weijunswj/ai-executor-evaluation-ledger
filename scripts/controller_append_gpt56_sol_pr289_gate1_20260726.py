#!/usr/bin/env python3
"""Append the controller-reviewed PR #289 Gate 1 architecture evaluation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "2026-07-26-gpt-5-6-sol-workflow-compatibility-gate1-reset-001"

RECORD = {
    "schema_version": 1,
    "record_type": "evaluation",
    "run_id": RUN_ID,
    "reviewed_at": "2026-07-26T20:31:00+08:00",
    "executor_reported_at": None,
    "provider": "OpenAI",
    "model": "GPT-5.6 Sol",
    "task_class": "architecture-review",
    "difficulty": "high",
    "subject_alias": "workflow-compatibility-a",
    "revision_binding": "exact-public-head-and-current-main-controller-verified",
    "prompt_sha256": None,
    "prompt_capture": "The complete controller Gate 1 prompt and executor architecture packet are preserved privately; no standalone prompt hash was computed.",
    "objective": [
        "produce a no-mutation architecture reset for the n8n Skills compatibility transaction and recovery lane",
        "close phase progression, evidence retirement, destructive-boundary stale-byte and duplicate-classification defects as one coherent design",
        "integrate the future implementation with the current accepted main revision without mutating the repository or live systems",
        "define exact crash, recovery, migration and Windows filesystem contracts suitable for a later controller design lock",
    ],
    "reported_operations": {
        "repository_mutations": 0,
        "github_mutations": 0,
        "live_system_actions": 0,
        "installed_cache_actions": 0,
        "focused_existing_tests_passed": 5,
        "controlled_runtime_experiments_performed": True,
    },
    "controller_verification": {
        "exact_pr_head_verified": True,
        "exact_current_main_verified": True,
        "all_four_prior_root_causes_independently_confirmed": True,
        "architecture_direction_materially_improved": True,
        "controller_review_id": 4781733483,
        "material_findings": 4,
        "highest_finding_severity": "P1",
        "gate_disposition": "gate_1_amend",
    },
    "outcome": "amend",
    "first_pass_accepted": False,
    "controller_intervention_required": True,
    "safe_final_state_reported": True,
    "safe_final_state_verified": True,
    "root_cause_identified": True,
    "follow_up_runs_required": 1,
    "scores": {
        "correctness": 3.8,
        "safety_and_scope_control": 5.0,
        "evidence_quality": 4.8,
        "operational_judgement": 3.6,
        "task_understanding": 4.6,
        "tracker_and_repository_hygiene": 4.8,
        "autonomy": 3.2,
        "efficiency": 3.2,
    },
    "weighted_score_5": 4.24,
    "weighted_score_10": 8.48,
    "integrity_and_control_flags": [
        "architecture_internal_conflict",
        "torn_append_recovery_undefined",
        "durability_adapter_unselected",
        "retirement_primitive_unselected",
        "tombstone_retention_unbounded_operationally",
    ],
    "verified_strengths": [
        "independently reproduced the four exact-head transaction and performance defects and accurately mapped their call paths",
        "proposed one coherent transaction-state-machine direction rather than four isolated patches",
        "made phase-30 winner recognition explicit, added final destructive-boundary tree validation and removed the duplicate healthy classification",
        "kept plugin refresh, installed-cache repair and consumer-repository helper propagation as separate authority domains",
        "preserved a clean repository, made zero GitHub mutations and accessed no installed cache or live system",
    ],
    "verified_defects": [
        "the append-only journal contract simultaneously treats a torn final append as a recoverable durable prefix and malformed evidence, leaving crash recovery undefined",
        "the journal's exact stable placement and supported write-through adapter were not selected, so its authority and durability boundary are not implementable yet",
        "retirement depends on preferred handle-bound Windows operations without selecting a supported implementation or a complete logical-retirement fallback",
        "permanent journal tombstones are only count-bounded and can eventually exhaust future repair authority without an exact safe retention or compaction contract",
    ],
    "next_evaluation": "amend Gate 1 architecture narrowly to define record framing and torn-tail adjudication, a stable journal location and supported durability adapter, an implementable retirement primitive or truthful fallback, and exact bounded tombstone retention; do not implement until the amended design is accepted and locked",
    "confidence": "anecdotal",
    "redaction_notice": "Public-safe controller evaluation using an opaque subject alias and no local paths, installed cache identity or private runtime details.",
}

FORBIDDEN_REASONING_FIELDS = {
    "requested_reasoning_level",
    "canonical_reasoning_level",
    "requested_provider_reasoning_mode",
    "observed_reasoning_mode",
    "observed_provider_reasoning_mode",
    "reasoning_mode_exposed",
}


def main() -> int:
    path = ROOT / "evaluations.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(record.get("run_id") == RUN_ID for record in records):
        raise SystemExit(f"Run already present: {RUN_ID}")
    leaked = FORBIDDEN_REASONING_FIELDS.intersection(RECORD)
    if leaked:
        raise SystemExit(f"Reasoning fields are forbidden: {sorted(leaked)}")
    if RECORD["provider"] != "OpenAI" or RECORD["model"] != "GPT-5.6 Sol":
        raise SystemExit("Unexpected model identity")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(RECORD, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
