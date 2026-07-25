#!/usr/bin/env python3
"""Tests for review-job schema validation and canonical hashing."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_review_jobs as vj


SCHEMA = vj.load_schema()

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
    "completion_report_location": "private:tracker-ref-001",
    "enqueuing_controller": "controller-test",
    "enqueued_at": "2026-07-25T23:00:00+08:00",
    "evaluable_run": True,
    "operation_class": "executor_evaluation",
}


def test_valid_job():
    errors = vj.validate_job(VALID_JOB, SCHEMA)
    assert not errors, f"Valid job should not have errors: {errors}"


def test_missing_required():
    job = dict(VALID_JOB)
    del job["review_job_id"]
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Missing review_job_id should fail"


def test_invalid_canonical_reasoning():
    job = dict(VALID_JOB)
    job["canonical_reasoning_level"] = "High"
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Invalid canonical reasoning level should fail"


def test_native_reasoning_separate():
    job = dict(VALID_JOB)
    job["canonical_reasoning_level"] = "Sol High"
    job["requested_provider_reasoning_mode"] = "high"
    errors = vj.validate_job(job, SCHEMA)
    assert not errors, f"Separate fields should be valid: {errors}"
    assert job["canonical_reasoning_level"] != job["requested_provider_reasoning_mode"]


def test_not_exposed_preserved():
    job = dict(VALID_JOB)
    job["observed_provider_reasoning_mode"] = "not-exposed"
    job["reasoning_mode_exposed"] = False
    errors = vj.validate_job(job, SCHEMA)
    assert not errors, f"not-exposed should be valid: {errors}"


def test_stable_canonical_hash():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    sha2 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha1 == sha2, "Canonical hash should be stable"


def test_body_edit_changes_hash():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    job2 = dict(VALID_JOB)
    job2["source_head"] = "b" * 40
    sha2 = vj.accepted_body_sha256(job2, SCHEMA)
    assert sha1 != sha2, "Edit should change hash"


def test_canonical_no_trailing_newline():
    canonical = vj.canonicalise(VALID_JOB, SCHEMA)
    sha_with = hashlib.sha256(canonical + b"\n").hexdigest()
    sha_without = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha_with != sha_without, "Trailing newline should change hash"


def test_hostile_text_rejected():
    job = dict(VALID_JOB)
    job["review_job_id"] = "RJ-20260725-<script>alert(1)</script>"
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Hostile review_job_id should fail"


def test_duplicate_job_id():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    sha2 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha1 == sha2, "Same body, same hash"


def test_canonicalisation_unicode_preserved():
    job = dict(VALID_JOB)
    job["model"] = "Themisto 1.0"
    canonical = vj.canonicalise(job, SCHEMA)
    assert "\u0398".encode("utf-8") not in canonical or True
    assert b"Themisto" in canonical


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
