import copy
import json
import hashlib
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
START_HEAD = "4eb94faed77336dea785b8f3009134b0515ef2d0"


class TestBatchProcessing(unittest.TestCase):
    def config(self, batch_id="batch-test-a005"):
        return ProcessBatchConfig(
            operating_mode="initial",
            base_sha=START_HEAD,
            canonical_main_sha=CANONICAL_MAIN,
            batch_id=batch_id,
            controller_run_id="controller-a005-test",
            pr_number=151,
            expected_head_sha=START_HEAD,
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
        receipt = json.loads(result["candidate_files"][receipt_path].decode("utf-8"))
        self.assertEqual(receipt["canonical_record_hashes"]["run-batch-a005"], sha256_bytes(line))
        self.assertEqual(receipt["terminal_outcome_count"], 2)
        self.assertEqual(len(receipt["comment_bindings"]), 2)
        self.assertNotIn(b"ordinary retained comment", result["candidate_files"][receipt_path])

    def test_incremental_uses_supplied_git_object_not_worktree_bytes(self):
        config = self.config("batch-incremental-a005")
        config = ProcessBatchConfig(**{
            **config.__dict__,
            "operating_mode": "incremental",
            "base_sha": START_HEAD,
            "canonical_main_sha": START_HEAD,
        })
        records = json.loads((ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(records["record_type"], "evaluation")
        result = build_batch_candidate(
            config,
            comments=self.comments(),
            queue_fetcher=self.queue(self.comments()),
            comment_fetcher=self.fetcher(self.comments()),
        )
        authority_line = next(line for line in result[0]["evaluations.jsonl"].splitlines(keepends=True) if b"2026-07-24-mimo-2-5-pro-project-a-stage-a-001" in line)
        worktree_line = (ROOT / "evaluations.jsonl").read_bytes().splitlines(keepends=True)[0]
        self.assertTrue(authority_line.endswith(b"\n"))
        self.assertNotEqual(authority_line, worktree_line)

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
