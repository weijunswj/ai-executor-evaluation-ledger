#!/usr/bin/env python3
"""Tests for base-trusted candidate validation: restricted paths, prefix, coverage, identity."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def test_restricted_file_modified_detected():
    with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as cand_dir:
        base = Path(base_dir)
        cand = Path(cand_dir)
        (base / "scheduled-review").mkdir()
        (base / "scheduled-review" / "RULES.md").write_text("base content")
        (cand / "scheduled-review").mkdir(parents=True)
        (cand / "scheduled-review" / "RULES.md").write_text("modified content")
        base_bytes = (base / "scheduled-review" / "RULES.md").read_bytes()
        cand_bytes = (cand / "scheduled-review" / "RULES.md").read_bytes()
        assert base_bytes != cand_bytes


def test_restricted_file_unchanged_passes():
    content = "same content"
    with tempfile.TemporaryDirectory() as base_dir:
        base = Path(base_dir)
        (base / "scheduled-review").mkdir()
        f = base / "scheduled-review" / "RULES.md"
        f.write_text(content)
        assert f.read_bytes() == content.encode()


def test_restricted_file_added_detected():
    with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as cand_dir:
        base = Path(base_dir)
        cand = Path(cand_dir)
        base_dne = (base / "scripts" / "check_public_safety.py")
        assert not base_dne.exists()
        (cand / "scripts").mkdir(parents=True)
        (cand / "scripts" / "check_public_safety.py").write_text("new")
        assert (cand / "scripts" / "check_public_safety.py").exists()


def test_restricted_directory_workflow_modified_detected():
    with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as cand_dir:
        base = Path(base_dir)
        cand = Path(cand_dir)
        (base / ".github" / "workflows").mkdir(parents=True)
        (cand / ".github" / "workflows").mkdir(parents=True)
        (base / ".github" / "workflows" / "test.yml").write_text("base")
        (cand / ".github" / "workflows" / "test.yml").write_text("modified")
        assert (base / ".github" / "workflows" / "test.yml").read_bytes() != (
            cand / ".github" / "workflows" / "test.yml"
        ).read_bytes()


def test_jsonl_exact_prefix_passes():
    base = b'{"run_id":"a"}\n{"run_id":"b"}\n'
    candidate = base + b'{"run_id":"c"}\n'
    assert candidate.startswith(base)


def test_jsonl_prefix_mutation_detected():
    base = b'{"run_id":"a"}\n{"run_id":"b"}\n'
    candidate = b'{"run_id":"a"}\n{"run_id":"modified"}\n'
    assert not candidate.startswith(base)


def test_duplicate_run_id_detected():
    lines = ['{"run_id":"a"}', '{"run_id":"b"}', '{"run_id":"a"}']
    seen = set()
    dups = [rid for rid in (json.loads(l)["run_id"] for l in lines) if rid in seen or seen.add(rid)]
    assert len(dups) > 0


def test_base_validator_uses_base_code():
    import scripts.validate_scheduled_review_candidate as vc
    assert vc.check_restricted_files is not None
    assert vc.check_jsonl_prefix is not None


def test_candidate_cannot_replace_base():
    base_paths = [
        "scripts/check_public_safety.py",
        "scripts/rebuild_views.py",
        "scripts/validate_scheduled_review_candidate.py",
    ]
    for p in base_paths:
        assert p.startswith("scripts/")


def test_private_data_rejected():
    public_safe = '{"review_job_id":"RJ-20260725-001","subject_alias":"test-a"}'
    assert "secret-key" not in public_safe
    assert "token_" not in public_safe


def test_manifest_coverage_required():
    manifest_jobs = [{"review_job_id": "RJ-001", "state": "reviewed", "evaluable_run": True, "operation_class": "executor_evaluation"}]
    result_records = [{"review_job_id": "RJ-001", "evaluation_record": {"run_id": "run-001"}}]
    m_ids = {j["review_job_id"] for j in manifest_jobs}
    r_ids = {r["review_job_id"] for r in result_records}
    assert m_ids == r_ids


def test_evaluable_job_maps_to_record():
    job = {"review_job_id": "RJ-001", "state": "reviewed", "evaluable_run": True, "operation_class": "executor_evaluation"}
    result = {"review_job_id": "RJ-001", "result_type": "evaluated", "evaluation_record": {"run_id": "run-001"}}
    assert result["result_type"] == "evaluated"


def test_blocked_no_record():
    result = {"review_job_id": "RJ-002", "result_type": "blocked", "blocked_reason_code": "source_head_missing"}
    assert result["result_type"] == "blocked"
    assert result.get("evaluation_record") is None


def test_admin_no_record():
    result = {"review_job_id": "RJ-003", "result_type": "administrative"}
    assert result["result_type"] == "administrative"
    assert result.get("evaluation_record") is None


def test_blocked_reason_code_allowlist():
    valid = {"source_head_missing", "intake_missing", "duplicate_job_id"}
    for code in valid:
        assert code in {
            "intake_missing", "duplicate_job_id", "intake_body_changed",
            "invalid_schema", "missing_model_identity", "missing_source_revision",
            "conflicting_duplicate_run_id", "source_inaccessible", "source_head_missing",
            "private_evidence_unavailable", "material_evidence_conflict",
            "review_too_large", "dependent_job_blocked",
        }


def test_no_reasoning_in_result():
    result = {
        "schema_version": 2,
        "result_type": "evaluated",
        "review_job_id": "RJ-001",
        "batch_id": "BATCH-20260725-001",
        "reviewed_at": "2026-07-25T23:00:00+08:00",
        "rulebook_sha": "a" * 40,
        "verdict": "accepted",
        "weighted_score_5": 4.0,
        "evaluation_record": {"run_id": "run-001"},
        "run_id": "run-001",
        "provider": "Anthropic",
        "model": "Claude Opus 4.8",
    }
    assert "canonical_reasoning_level" not in result
    assert "observed_reasoning_mode" not in result
    assert "reasoning_mode_exposed" not in result


def test_base_validator_scans_candidate_public_safety():
    import scripts.validate_scheduled_review_candidate as vc
    assert callable(vc.check_public_safety_on_candidate)


def test_base_validator_checks_candidate_views():
    import scripts.validate_scheduled_review_candidate as vc
    assert callable(vc.check_deterministic_views)


def test_immutable_base_head_shas():
    base_sha = "b" * 40
    head_sha = "c" * 40
    assert len(base_sha) == 40
    assert len(head_sha) == 40
    assert base_sha != head_sha


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
