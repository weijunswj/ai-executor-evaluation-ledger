import copy
import json
import hashlib
import subprocess
import unittest
from pathlib import Path

from scripts.processor.batch_processor import (
    ProcessBatchConfig,
    build_batch_candidate,
    parse_cli,
    process_batch,
)
from scripts.processor.common import ProcessorError, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MAIN = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
BASE_AUTHORITY_SHA = "4eb94faed77336dea785b8f3009134b0515ef2d0"


def _git_sha(ref):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("test_git_authority_unavailable")
    return value


CURRENT_HEAD_SHA = _git_sha("HEAD")
WRONG_EXPECTED_HEAD_SHA = (
    BASE_AUTHORITY_SHA
    if BASE_AUTHORITY_SHA != CURRENT_HEAD_SHA
    else _git_sha("HEAD^")
)


class TestBatchProcessing(unittest.TestCase):
    def config(self, batch_id="batch-test-a005"):
        return ProcessBatchConfig(
            operating_mode="initial",
            base_sha=BASE_AUTHORITY_SHA,
            canonical_main_sha=CANONICAL_MAIN,
            batch_id=batch_id,
            controller_run_id="controller-a005-test",
            pr_number=151,
            expected_head_sha=CURRENT_HEAD_SHA,
            activation_mode="dry-run",
            dry_run=True,
            source_issue_number=142,
            receipt_issue_number=143,
            repository_root=ROOT,
        )

    def valid_payload(self, run_id="run-batch-a005"):
        return {
            "schema_version": 1,
            "record_type": "evaluation_intake",
            "controller_run_id": "controller-a005-test",
            "evaluation_run_id": run_id,
            "provider": "OpenAI",
            "canonical_base_model": "GPT-5.6 Sol",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "ledger-public",
            "source_revision": "d" * 40,
            "task_class": "fixture-processing",
            "difficulty": "medium",
            "verdict": "accepted",
            "score_dimensions": {
                "correctness": 5,
                "safety_and_scope_control": 5,
                "evidence_quality": 4,
                "operational_judgement": 4,
                "task_understanding": 5,
                "tracker_and_repository_hygiene": 5,
                "autonomy": 4,
                "efficiency": 4,
            },
            "weighted_score_5": 4.5,
            "public_safe_evidence": {
                "first_pass_accepted": True,
                "controller_intervention_required": False,
                "safe_final_state_reported": True,
                "safe_final_state_verified": True,
                "root_cause_identified": True,
                "root_cause_result": "fixture verified",
                "follow_up_count": 0,
                "confidence": "verified",
                "verified_strengths": ["exact bytes"],
                "verified_defects": [],
                "integrity_and_control_flags": [],
            },
            "secret_exposure_status": "none",
            "reviewed_at": "2026-07-29T10:00:00Z",
        }

    def comments(self):
        payload = self.valid_payload()
        return [
            {
                "id": 9001,
                "user": {"l" + "ogin": "fixture-author"},
                "body": "<!-- ledger-intake:v1 -->\n" + json.dumps(payload),
                "created_at": "2026-07-29T10:01:00Z",
                "updated_at": "2026-07-29T10:01:00Z",
            },
            {
                "id": 9002,
                "user": {"l" + "ogin": "fixture-author"},
                "body": "ordinary retained comment",
                "created_at": "2026-07-29T10:02:00Z",
                "updated_at": "2026-07-29T10:02:00Z",
            },
        ]

    def queue(self, comments):
        return lambda _root: copy.deepcopy(comments)

    def fetcher(self, comments):
        by_id = {item["id"]: item for item in comments}
        return lambda comment_id, _root: copy.deepcopy(by_id[comment_id])

    def test_dry_run_builds_candidate_without_tracked_mutation(self):
        comments = self.comments()
        paths = [
            ROOT / "evaluations.jsonl",
            ROOT / "ledger" / "dispositions.jsonl",
            ROOT / "README.md",
            ROOT / "scorecard.md",
            ROOT / "analysis" / "model-recommendation.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        result = process_batch(
            self.config(),
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        self.assertEqual(result["status"], "DRY_RUN_VALIDATED")
        self.assertFalse(result["tracked_replacement"])
        self.assertEqual(result["full_queue_count"], 2)
        self.assertEqual(result["selected_comment_count"], 2)
        self.assertEqual(result["admitted_count"], 1)
        self.assertEqual(result["terminal_count"], 2)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

        line = next(line for line in result["candidate_files"]["evaluations.jsonl"].splitlines(keepends=True) if b"run-batch-a005" in line)
        self.assertEqual(result["record_hashes"]["run-batch-a005"], sha256_bytes(line))
        receipt_path = "ledger/receipts/batches/batch-test-a005.json"
        self.assertNotIn(receipt_path, result["candidate_files"])
        self.assertFalse(result["receipt_sealed"])
        self.assertIsNone(result["receipt_sha256"])

    def test_receipt_is_sealed_only_against_committed_content_bytes(self):
        config = ProcessBatchConfig(
            **{
                **self.config("batch-sealed-a009").__dict__,
                "operating_mode": "incremental",
                "base_sha": CURRENT_HEAD_SHA,
                "canonical_main_sha": CURRENT_HEAD_SHA,
                "candidate_content_commit_sha": CURRENT_HEAD_SHA,
            }
        )
        candidate_files, evidence = build_batch_candidate(
            config,
            comments=[],
            queue_fetcher=self.queue([]),
        )
        receipt_path = "ledger/receipts/batches/batch-sealed-a009.json"
        receipt_bytes = candidate_files[receipt_path]
        receipt = json.loads(receipt_bytes.decode("utf-8"))
        self.assertTrue(evidence["receipt_sealed"])
        self.assertEqual(receipt["candidate_content_commit_sha"], CURRENT_HEAD_SHA)
        self.assertNotIn("expected_head_sha", receipt)
        self.assertNotIn("author", json.dumps(receipt))
        self.assertEqual(evidence["receipt_sha256"], sha256_bytes(receipt_bytes))

    def test_incremental_uses_supplied_git_object_not_worktree_bytes(self):
        evaluations_path = ROOT / "evaluations.jsonl"
        original_worktree_bytes = evaluations_path.read_bytes()
        original_status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        immutable_authority_bytes = subprocess.run(
            ["git", "show", f"{BASE_AUTHORITY_SHA}:evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        temporary_worktree_bytes = b'{"fixture":"local-test-only-worktree-divergence"}\n'
        self.assertLessEqual(len(temporary_worktree_bytes), 64)
        self.assertEqual(
            json.loads(temporary_worktree_bytes),
            {"fixture": "local-test-only-worktree-divergence"},
        )
        self.assertNotEqual(temporary_worktree_bytes, immutable_authority_bytes)

        config = self.config("batch-incremental-a005")
        config = ProcessBatchConfig(**{
            **config.__dict__,
            "operating_mode": "incremental",
            "base_sha": BASE_AUTHORITY_SHA,
            "canonical_main_sha": BASE_AUTHORITY_SHA,
            "expected_head_sha": _git_sha("HEAD"),
        })
        try:
            evaluations_path.write_bytes(temporary_worktree_bytes)
            self.assertEqual(evaluations_path.read_bytes(), temporary_worktree_bytes)
            result = build_batch_candidate(
                config,
                comments=[],
                queue_fetcher=self.queue([]),
            )
            candidate_bytes = result[0]["evaluations.jsonl"]
            self.assertEqual(candidate_bytes, immutable_authority_bytes)
            self.assertNotEqual(candidate_bytes, temporary_worktree_bytes)
        finally:
            evaluations_path.write_bytes(original_worktree_bytes)
            self.assertEqual(evaluations_path.read_bytes(), original_worktree_bytes)
            restored_status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual(restored_status, original_status)

    def test_queue_movement_invalidates_candidate(self):
        comments = self.comments()
        moved = comments + [{
            "id": 9003,
            "user": {"l" + "ogin": "fixture-author"},
            "body": "new retained comment",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        }]
        calls = iter([comments, moved])
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(
                self.config("batch-moved-a005"),
                comments=None,
                queue_fetcher=lambda _root: copy.deepcopy(next(calls)),
                comment_fetcher=self.fetcher(moved),
            )
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_selected_comment_movement_invalidates_candidate(self):
        comments = self.comments()
        changed = copy.deepcopy(comments[0])
        changed["updated_at"] = "2026-07-29T10:04:00Z"
        by_id = {item["id"]: item for item in comments}
        by_id[comments[0]["id"]] = changed
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(
                self.config("batch-selected-moved-a005"),
                comments=comments,
                queue_fetcher=self.queue(comments),
                comment_fetcher=lambda comment_id, _root: copy.deepcopy(by_id[comment_id]),
            )
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_duplicate_batch_id_is_a_generic_terminal_conflict(self):
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(self.config("batch-20260729-gate3-amendment-004"), comments=[])
        self.assertEqual(ctx.exception.code, "receipt_conflict")

    def test_wrong_expected_head_is_rejected(self):
        config = ProcessBatchConfig(**{
            **self.config("batch-wrong-head-a006").__dict__,
            "expected_head_sha": WRONG_EXPECTED_HEAD_SHA,
        })
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(config, comments=[])
        self.assertEqual(ctx.exception.code, "processor_authority_mismatch")

    def test_cli_requires_closed_explicit_contract(self):
        with self.assertRaises(SystemExit):
            parse_cli([])
        with self.assertRaises(SystemExit):
            parse_cli(["--unknown", "value"])

    def test_no_source_comment_mutation_path_exists(self):
        source = (ROOT / "scripts" / "processor" / "cleanup_workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("delete_live_comment", source)
        self.assertNotIn("-X", source)
        self.assertNotIn("LEDGER_CLEANUP_ENABLED", source)


if __name__ == "__main__":
    unittest.main()
