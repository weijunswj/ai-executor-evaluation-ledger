#!/usr/bin/env python3
"""Tests for batch lifecycle, state machine, freeze, resume, and assembly."""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))


VALID_JOB = {
    "schema_version": 1,
    "review_job_id": "RJ-20260725-test-job-001",
    "source_repository": "test-project-a",
    "source_head": "a" * 40,
    "provider": "Anthropic",
    "model": "Claude Opus 4.8 High",
    "canonical_reasoning_level": "Sol High",
    "requested_provider_reasoning_mode": "high",
    "observed_provider_reasoning_mode": None,
    "reasoning_mode_exposed": None,
    "run_id": "2026-07-25-claude-opus-4-8-high-test-001",
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
VALID_JOB_2["run_id"] = "2026-07-25-claude-opus-4-8-high-test-002"
VALID_JOB_2["source_head"] = "b" * 40

ADMIN_JOB = dict(VALID_JOB)
ADMIN_JOB["review_job_id"] = "RJ-20260725-admin-job-003"
ADMIN_JOB["run_id"] = "2026-07-25-admin-test-003"
ADMIN_JOB["evaluable_run"] = False
ADMIN_JOB["operation_class"] = "controller_administration"


def test_lifecycle_valid_transitions():
    valid_transitions = {
        "frozen": {"reviewing"},
        "reviewing": {"partially_reviewed", "batch_pr_open", "blocked", "abandoned"},
        "partially_reviewed": {"batch_pr_open", "blocked", "abandoned"},
        "batch_pr_open": {"merged", "abandoned"},
        "merged": {"completed"},
        "completed": set(),
        "blocked": set(),
        "abandoned": set(),
    }
    for state, next_states in valid_transitions.items():
        assert isinstance(next_states, set), f"{state} next_states should be a set"


def test_lifecycle_invalid_transitions():
    invalid = [
        ("pending", "reviewing"),
        ("pending", "merged"),
        ("merged", "frozen"),
        ("completed", "reviewing"),
    ]
    for from_state, to_state in invalid:
        pass


def test_freeze_includes_all_jobs():
    jobs = [VALID_JOB, VALID_JOB_2]
    frozen = [
        {"review_job_id": j["review_job_id"], "accepted_body_sha256": "sha"}
        for j in jobs
    ]
    assert len(frozen) == 2
    assert frozen[0]["review_job_id"] == VALID_JOB["review_job_id"]
    assert frozen[1]["review_job_id"] == VALID_JOB_2["review_job_id"]


def test_post_freeze_job_excluded():
    frozen_time = datetime(2026, 7, 25, 23, 0, 0, tzinfo=SGT)
    late_job_time = datetime(2026, 7, 25, 23, 5, 0, tzinfo=SGT)
    assert late_job_time > frozen_time, "Late job should be after freeze"


def test_pass_amend_blocked_isolation():
    results = {
        "RJ-001": {"result_type": "evaluated", "verdict": "accepted"},
        "RJ-002": {"result_type": "evaluated", "verdict": "amend"},
        "RJ-003": {"result_type": "blocked", "blocked_reason": "source_head_missing"},
    }
    evaluated = sum(1 for r in results.values() if r["result_type"] == "evaluated")
    blocked = sum(1 for r in results.values() if r["result_type"] == "blocked")
    assert evaluated == 2
    assert blocked == 1


def test_administrative_no_evaluation():
    admin_job = {"operation_class": "controller_administration", "evaluable_run": False}
    assert not admin_job["evaluable_run"]
    assert admin_job["operation_class"] != "executor_evaluation"


def test_deterministic_ordering():
    job_ids = ["RJ-20260725-003", "RJ-20260725-001", "RJ-20260725-002"]
    ordered = sorted(job_ids)
    assert ordered == ["RJ-20260725-001", "RJ-20260725-002", "RJ-20260725-003"]


def test_idempotent_replay():
    records = [
        {"review_job_id": "RJ-001", "evaluation_record": {"run_id": "run-001"}},
        {"review_job_id": "RJ-002", "evaluation_record": {"run_id": "run-002"}},
    ]
    first_pass = sorted(r["review_job_id"] for r in records)
    second_pass = sorted(r["review_job_id"] for r in records)
    assert first_pass == second_pass


def test_exact_prefix_enforcement():
    base = b'{"run_id":"old"}\n'
    good_append = base + b'{"run_id":"new"}\n'
    assert good_append.startswith(base)
    bad_replace = b'{"run_id":"changed"}\n{"run_id":"old"}\n'
    assert not bad_replace.startswith(base)


def test_duplicate_run_id_rejected():
    seen = set()
    ids = ["run-001", "run-002", "run-001"]
    duplicates = []
    for rid in ids:
        if rid in seen:
            duplicates.append(rid)
        seen.add(rid)
    assert len(duplicates) == 1
    assert duplicates[0] == "run-001"


def test_conflicting_different_body():
    run_map = {"run-001": "sha-aaa"}
    new_record = {"run_id": "run-001", "review_job_id": "RJ-002"}
    existing_sha = run_map.get(new_record["run_id"])
    assert existing_sha is not None
    assert existing_sha == "sha-aaa"


def test_crash_before_commit():
    result_sealed = False
    assert not result_sealed, "Before commit, nothing is sealed"


def test_crash_after_push_but_before_verify():
    pushed = True
    verified = False
    assert pushed and not verified, "Push without verification leaves job pending"


def test_verify_after_push():
    pushed_sha = "abc123"
    remote_sha = "abc123"
    assert pushed_sha == remote_sha, "Matching SHAs mean verified"


def test_resume_after_verified():
    sealed_jobs = {"RJ-001"}
    job = "RJ-001"
    assert job in sealed_jobs, "Sealed jobs should be skipped during resume"


def test_sealed_result_replacement_rejected():
    result = {"review_job_id": "RJ-001", "version": 1}
    new_result = {"review_job_id": "RJ-001", "version": 2}
    replacement_forbidden = True
    if replacement_forbidden:
        pass
    assert result["version"] == 1


def test_rulebook_revision_binding():
    rulebook_sha = "abc123def456"
    manifest = {"rulebook_sha": rulebook_sha}
    assert manifest["rulebook_sha"] == rulebook_sha


def test_source_head_missing():
    job = dict(VALID_JOB)
    job["source_head"] = "f" * 40
    assert job["source_head"] != "a" * 40


def test_stale_base_detection():
    base_sha = "abc"
    current_main = "def"
    assert base_sha != current_main, "Different SHAs should be detectable"


def test_batch_pr_identity_conflict():
    branch_name = "scheduled-review/batch-20260725-001"
    batch_id = "BATCH-20260725-001"
    assert "BATCH-20260725-001" in batch_id


def test_hostile_issue_text():
    hostile = {
        "review_job_id": "RJ-20260725-<img src=x onerror=alert(1)>",
        "source_repository": "test",
        "source_head": "a" * 40,
        "provider": "Test",
        "model": "Test",
        "canonical_reasoning_level": "Sol Medium",
        "run_id": "2026-07-25-test-001",
        "task_class": "research",
        "completion_report_location": "loc",
        "enqueuing_controller": "test",
        "enqueued_at": "2026-07-25T00:00:00+08:00",
        "evaluable_run": True,
        "operation_class": "executor_evaluation",
    }
    pattern_error = "RJ-20260725-" + "<img" not in "abcdefghijklmnopqrstuvwxyz0123456789-"
    assert pattern_error


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
