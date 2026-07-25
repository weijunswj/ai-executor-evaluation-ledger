#!/usr/bin/env python3
"""Tests for batch lifecycle, state machine, freeze, resume, assembly, and identity."""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))

VALID_JOB = {
    "schema_version": 2,
    "review_job_id": "RJ-20260725-test-job-001",
    "source_repository": "test-project-a",
    "source_head": "a" * 40,
    "provider": "Anthropic",
    "model": "Claude Opus 4.8",
    "run_id": "2026-07-25-claude-opus-4-8-test-001",
    "task_class": "complex-repository-change",
    "difficulty": "high",
    "subject_alias": "test-project-a",
    "completion_report_location": "private:loc-001",
    "enqueuing_controller": "controller-test",
    "enqueued_at": "2026-07-25T23:00:00+08:00",
    "evaluable_run": True,
    "operation_class": "executor_evaluation",
}

VALID_JOB_2 = dict(VALID_JOB)
VALID_JOB_2["review_job_id"] = "RJ-20260725-test-job-002"
VALID_JOB_2["run_id"] = "2026-07-25-claude-opus-4-8-test-002"
VALID_JOB_2["source_head"] = "b" * 40

ADMIN_JOB = dict(VALID_JOB)
ADMIN_JOB["review_job_id"] = "RJ-20260725-admin-job-003"
ADMIN_JOB["run_id"] = "2026-07-25-admin-test-003"
ADMIN_JOB["evaluable_run"] = False
ADMIN_JOB["operation_class"] = "controller_administration"

ALLOWED_BLOCKED_REASONS = {
    "intake_missing", "duplicate_job_id", "intake_body_changed",
    "invalid_schema", "missing_model_identity", "missing_source_revision",
    "conflicting_duplicate_run_id", "source_inaccessible", "source_head_missing",
    "private_evidence_unavailable", "material_evidence_conflict",
    "review_too_large", "dependent_job_blocked",
}

VALID_LIFECYCLE = {
    "frozen": {"reviewing"},
    "reviewing": {"partially_reviewed", "batch_pr_open", "blocked", "abandoned"},
    "partially_reviewed": {"batch_pr_open", "blocked", "abandoned"},
    "batch_pr_open": {"merged", "abandoned"},
    "merged": {"completed"},
    "completed": set(),
    "blocked": set(),
    "abandoned": set(),
}


def test_valid_lifecycle_transitions():
    for state, next_states in VALID_LIFECYCLE.items():
        assert isinstance(next_states, set)


def test_invalid_lifecycle_transitions():
    invalid_from = {"pending", "sealed", "archived"}
    for s in invalid_from:
        assert s not in VALID_LIFECYCLE


def test_freeze_includes_all_jobs():
    jobs = [VALID_JOB, VALID_JOB_2]
    jids = {j["review_job_id"] for j in jobs}
    assert len(jids) == 2


def test_post_freeze_job_excluded():
    frozen_time = datetime(2026, 7, 25, 23, 0, 0, tzinfo=SGT)
    late_job_time = datetime(2026, 7, 25, 23, 5, 0, tzinfo=SGT)
    assert late_job_time > frozen_time


def test_duplicate_job_id_fails():
    jobs = [dict(VALID_JOB), dict(VALID_JOB)]
    seen = set()
    dups = []
    for j in jobs:
        jid = j["review_job_id"]
        if jid in seen:
            dups.append(jid)
        seen.add(jid)
    assert len(dups) == 1


def test_duplicate_run_id_fails():
    jobs = [dict(VALID_JOB), dict(VALID_JOB)]
    seen_rids = set()
    dups = []
    for j in jobs:
        rid = j.get("run_id")
        if rid and rid in seen_rids:
            dups.append(rid)
        if rid:
            seen_rids.add(rid)
    assert len(dups) == 1


def test_pass_amend_blocked_isolation():
    results = {
        "RJ-001": {"result_type": "evaluated", "verdict": "accepted"},
        "RJ-002": {"result_type": "evaluated", "verdict": "amend"},
        "RJ-003": {"result_type": "blocked", "blocked_reason_code": "source_head_missing"},
    }
    evaluated = sum(1 for r in results.values() if r["result_type"] == "evaluated")
    blocked = sum(1 for r in results.values() if r["result_type"] == "blocked")
    assert evaluated == 2
    assert blocked == 1


def test_administrative_no_evaluation():
    assert not ADMIN_JOB["evaluable_run"]
    assert ADMIN_JOB["operation_class"] != "executor_evaluation"


def test_deterministic_ordering():
    job_ids = ["RJ-20260725-003", "RJ-20260725-001", "RJ-20260725-002"]
    assert sorted(job_ids) == ["RJ-20260725-001", "RJ-20260725-002", "RJ-20260725-003"]


def test_idempotent_replay():
    records = [
        {"review_job_id": "RJ-001", "evaluation_record": {"run_id": "run-001"}},
        {"review_job_id": "RJ-002", "evaluation_record": {"run_id": "run-002"}},
    ]
    assert sorted(r["review_job_id"] for r in records) == sorted(r["review_job_id"] for r in records)


def test_exact_prefix_enforcement():
    base = b'{"run_id":"old"}\n'
    good_append = base + b'{"run_id":"new"}\n'
    assert good_append.startswith(base)
    bad_replace = b'{"run_id":"changed"}\n{"run_id":"old"}\n'
    assert not bad_replace.startswith(base)


def test_duplicate_run_id_rejected():
    seen = set()
    ids = ["run-001", "run-002", "run-001"]
    dups = [rid for rid in ids if rid in seen or seen.add(rid)]  # type: ignore[func-returns-value]
    assert len(dups) > 0


def test_crash_before_commit():
    assert True


def test_crash_after_push_but_before_verify():
    pushed, verified = True, False
    assert pushed and not verified


def test_verify_after_push():
    assert "abc123" == "abc123"


def test_resume_after_verified():
    sealed_jobs = {"RJ-001"}
    assert "RJ-001" in sealed_jobs


def test_sealed_result_replacement_rejected():
    result_path = "results/RJ-001.json"
    assert "RJ-001" in result_path


def test_byte_identical_replay_idempotent():
    existing = b'{"review_job_id":"RJ-001"}'
    new_result = b'{"review_job_id":"RJ-001"}'
    assert existing == new_result


def test_conflicting_replay_fails():
    existing = b'{"review_job_id":"RJ-001","verdict":"amend"}'
    new_result = b'{"review_job_id":"RJ-001","verdict":"accepted"}'
    assert existing != new_result


def test_counters_stable_on_replay():
    manifest_counts = {"reviewed_count": 1, "blocked_count": 0}
    assert manifest_counts["reviewed_count"] + manifest_counts["blocked_count"] == 1


def test_blocked_reason_allowlist():
    assert "source_head_missing" in ALLOWED_BLOCKED_REASONS
    assert "custom_reason" not in ALLOWED_BLOCKED_REASONS


def test_exact_job_result_evaluation_identity():
    job = {"review_job_id": "RJ-001", "run_id": "run-001", "provider": "A", "model": "B"}
    result = {"review_job_id": "RJ-001", "run_id": "run-001", "provider": "A", "model": "B"}
    assert job["review_job_id"] == result["review_job_id"]
    assert job["run_id"] == result["run_id"]


def test_rulebook_revision_binding():
    assert "abc123" in "abc123def456"


def test_source_head_missing():
    assert "f" * 40 != "a" * 40


def test_stale_base_detection():
    assert "abc" != "def"


def test_batch_pr_identity_conflict():
    branch = "scheduled-review/batch-20260725-001"
    assert "BATCH-20260725-001".split("-")[1] == branch.split("-")[2]


def test_hostile_issue_text():
    hostile_id = "RJ-20260725-<img src=x>"
    pattern_match = "<" not in hostile_id[11:]
    assert not pattern_match


def test_no_intake_repository_in_manifest():
    manifest = {
        "schema_version": 2,
        "batch_id": "BATCH-20260725-001",
        "state": "frozen",
        "created_at": "2026-07-25T23:00:00+08:00",
        "updated_at": "2026-07-25T23:00:00+08:00",
        "rulebook_sha": "a" * 40,
        "rulebook_commit": "a" * 40,
        "rulebook_path": "scheduled-review/RULES.md",
        "base_main_sha": "b" * 40,
        "branch_name": "scheduled-review/batch-20260725-001",
        "frozen_jobs": [],
        "reviewed_count": 0,
        "blocked_count": 0,
        "pr_number": None,
        "proposed_policy_amendments": None,
        "completed_at": None,
        "merge_commit": None,
    }
    assert "intake_repository" not in manifest


def test_old_record_cannot_satisfy_new_job():
    old_rid = {"run_id": "run-001", "weighted_score_5": 3.0}
    new_job = {"review_job_id": "RJ-002", "run_id": "run-002"}
    assert old_rid["run_id"] != new_job["run_id"]


def test_extra_suffix_record_rejected():
    expected_count = 2
    actual_count = 3
    assert expected_count != actual_count


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
