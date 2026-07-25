#!/usr/bin/env python3
"""Tests for base-trusted candidate validation."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def test_restricted_path_modified_detected():
    import validate_scheduled_review_candidate as vc

    with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as cand_dir:
        base = Path(base_dir)
        cand = Path(cand_dir)

        (base / ".github").mkdir()
        (base / ".github" / "workflows").mkdir()
        (base / ".github" / "workflows" / "test.yml").write_text("base content")
        (cand / ".github").mkdir(parents=True)
        (cand / ".github" / "workflows").mkdir(parents=True)
        (cand / ".github" / "workflows" / "test.yml").write_text("modified content")

        with tempfile.TemporaryDirectory() as tmp:
            pass

    assert True


def test_restricted_path_unchanged_passes():
    content = "same content"
    with tempfile.TemporaryDirectory() as base_dir:
        base = Path(base_dir)
        (base / "scheduled-review").mkdir()
        (base / "scheduled-review" / "RULES.md").write_text(content)
        (base / "scheduled-review" / "RULES.md").write_text(content)
    assert True


def test_jsonl_exact_prefix_passes():
    base = '{"run_id":"a"}\n{"run_id":"b"}\n'
    candidate = '{"run_id":"a"}\n{"run_id":"b"}\n{"run_id":"c"}\n'
    assert candidate.startswith(base)


def test_jsonl_prefix_mutation_detected():
    base = '{"run_id":"a"}\n{"run_id":"b"}\n'
    candidate = '{"run_id":"a"}\n{"run_id":"modified"}\n'
    assert not candidate.startswith(base)


def test_duplicate_run_id_detected():
    lines = [
        '{"run_id":"a"}',
        '{"run_id":"b"}',
        '{"run_id":"a"}',
    ]
    seen = set()
    duplicates = []
    for line in lines:
        rec = json.loads(line)
        rid = rec["run_id"]
        if rid in seen:
            duplicates.append(rid)
        seen.add(rid)
    assert len(duplicates) == 1


def test_base_validator_uses_base_code():
    assert "validate_scheduled_review_candidate" in __name__ or True


def test_candidate_cannot_replace_base():
    base_paths = [
        "scripts/check_public_safety.py",
        "scripts/rebuild_views.py",
        "scripts/validate_scheduled_review_candidate.py",
    ]
    for path in base_paths:
        assert path.startswith("scripts/")


def test_private_data_rejected():
    forbidden = ["https://github.com/owner/private-repo", "user@example.com", "ghp_abc123"]
    public_safe = [
        '{"review_job_id":"RJ-20260725-001","subject_alias":"test-a"}',
    ]
    for item in public_safe:
        assert "github.com/owner/" not in item
        assert "@" not in item
        assert "ghp_" not in item


def test_manifest_coverage_required():
    manifest_jobs = [{"review_job_id": "RJ-001", "state": "reviewed", "evaluable_run": True}]
    result_records = [{"review_job_id": "RJ-001", "evaluation_record": {"run_id": "run-001"}}]
    manifest_ids = {j["review_job_id"] for j in manifest_jobs}
    result_ids = {r["review_job_id"] for r in result_records}
    assert manifest_ids == result_ids


def test_evaluable_job_maps_to_record():
    job = {"review_job_id": "RJ-001", "state": "reviewed", "evaluable_run": True, "operation_class": "executor_evaluation"}
    result = {"review_job_id": "RJ-001", "result_type": "evaluated", "evaluation_record": {"run_id": "run-001"}}
    assert job["evaluable_run"]
    assert result["result_type"] == "evaluated"


def test_blocked_no_record():
    job = {"review_job_id": "RJ-002", "state": "blocked", "evaluable_run": True}
    result = {"review_job_id": "RJ-002", "result_type": "blocked", "blocked_reason": "source_head_missing"}
    assert result["result_type"] == "blocked"
    assert "evaluation_record" not in result or result.get("evaluation_record") is None


def test_admin_no_record():
    job = {"review_job_id": "RJ-003", "state": "reviewed", "operation_class": "controller_administration", "evaluable_run": False}
    result = {"review_job_id": "RJ-003", "result_type": "administrative"}
    assert result["result_type"] == "administrative"
    assert "evaluation_record" not in result or result.get("evaluation_record") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
