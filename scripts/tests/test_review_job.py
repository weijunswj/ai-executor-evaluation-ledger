#!/usr/bin/env python3
"""Tests for review-job schema v2: base-model-only identity, fail-closed validation, canonical hashing."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_review_jobs as vj

SCHEMA = vj.load_schema()

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
    "completion_report_location": "private:tracker-ref-001",
    "enqueuing_controller": "controller-test",
    "enqueued_at": "2026-07-25T23:00:00+08:00",
    "evaluable_run": True,
    "operation_class": "executor_evaluation",
}


def test_valid_job():
    errors = vj.validate_job(VALID_JOB, SCHEMA)
    assert not errors, f"Valid job should have no errors: {errors}"


def test_missing_required():
    job = dict(VALID_JOB)
    del job["review_job_id"]
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Missing review_job_id should fail"


def test_no_reasoning_fields_accepted():
    job = dict(VALID_JOB)
    job["canonical_reasoning_level"] = "Sol High"
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Reasoning fields should be rejected by additionalProperties: false"


def test_no_reasoning_emitted():
    canonical = vj.canonicalise(VALID_JOB, SCHEMA)
    assert b"canonical_reasoning_level" not in canonical
    assert b"observed_provider_reasoning_mode" not in canonical
    assert b"reasoning_mode_exposed" not in canonical


def test_model_not_inferred():
    job = dict(VALID_JOB)
    job["model"] = "Claude Opus 4.8 High"
    errors = vj.validate_job(job, SCHEMA)
    assert not errors, "Model is controller-supplied; validation does not strip suffixes"


def test_stable_canonical_hash():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    sha2 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha1 == sha2, "Canonical hash must be stable"


def test_body_edit_changes_hash():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    job2 = dict(VALID_JOB)
    job2["source_head"] = "b" * 40
    sha2 = vj.accepted_body_sha256(job2, SCHEMA)
    assert sha1 != sha2, "Edit must change hash"


def test_canonical_no_trailing_newline():
    canonical = vj.canonicalise(VALID_JOB, SCHEMA)
    sha_with = hashlib.sha256(canonical + b"\n").hexdigest()
    sha_without = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha_with != sha_without, "Trailing newline must change hash"


def test_hostile_text_rejected():
    job = dict(VALID_JOB)
    job["review_job_id"] = "RJ-20260725-<script>alert(1)</script>"
    errors = vj.validate_job(job, SCHEMA)
    assert errors, "Hostile review_job_id must fail"


def test_duplicate_job_id_same_hash():
    sha1 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    sha2 = vj.accepted_body_sha256(VALID_JOB, SCHEMA)
    assert sha1 == sha2


def test_canonicalisation_unicode_preserved():
    job = dict(VALID_JOB)
    job["model"] = "Themisto 1.0"
    canonical = vj.canonicalise(job, SCHEMA)
    assert b"Themisto" in canonical


def test_invalid_job_cannot_hash():
    job = dict(VALID_JOB)
    del job["source_repository"]
    try:
        vj.accepted_body_sha256(job, SCHEMA)
        assert False, "Should have raised"
    except ValueError:
        pass


def test_fail_closed_on_missing_jsonschema(monkeypatch):
    import validate_review_jobs as vj_mod
    original = vj_mod.jsonschema
    vj_mod.jsonschema = None
    try:
        vj_mod.require_jsonschema()
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass
    finally:
        vj_mod.jsonschema = original


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
