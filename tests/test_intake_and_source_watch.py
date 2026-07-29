import unittest
import json
from scripts.processor.intake_parser import parse_intake_comment, contains_reasoning_keys
from scripts.processor.source_watch import SourceWatchPlanner

class TestIntakeAndSourceWatch(unittest.TestCase):
    def setUp(self):
        self.planner = SourceWatchPlanner()
        self.recorded_ids = {"existing-run-001"}
        self.valid_payload = {
            "schema_version": 1,
            "record_type": "evaluation_intake",
            "controller_run_id": "ctrl-001",
            "evaluation_run_id": "new-run-002",
            "provider": "Google",
            "canonical_base_model": "Gemini 3.6 Flash",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "repo-a",
            "issue_number": 100,
            "pull_request_number": 101,
            "source_revision": "abc1234",
            "task_class": "research",
            "difficulty": "medium",
            "verdict": "accepted",
            "score_dimensions": {"correctness": 5.0, "safety_and_scope_control": 5.0, "evidence_quality": 5.0, "operational_judgement": 5.0, "task_understanding": 5.0, "tracker_and_repository_hygiene": 5.0, "autonomy": 5.0, "efficiency": 5.0},
            "weighted_score_5": 5.0,
            "public_safe_evidence": {"verified_strengths": ["Clean implementation"]},
            "secret_exposure_status": "none"
        }

    def test_valid_intake_admission(self):
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload)
        disp, payload, reason = parse_intake_comment(1001, body, self.recorded_ids, set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(payload["evaluation_run_id"], "new-run-002")

    def test_byte_zero_marker_enforcement(self):
        body = "Invalid prefix <!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload)
        disp, _, _ = parse_intake_comment(1002, body, self.recorded_ids, set())
        self.assertEqual(disp, "malformed")

    def test_reasoning_key_rejection_nested(self):
        payload = dict(self.valid_payload)
        payload["public_safe_evidence"]["observed_reasoning_mode"] = "high"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, _, reason = parse_intake_comment(1003, body, self.recorded_ids, set())
        self.assertEqual(disp, "malformed")
        self.assertIn("reasoning", reason)

    def test_already_recorded_deduplication(self):
        payload = dict(self.valid_payload)
        payload["evaluation_run_id"] = "existing-run-001"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, _, _ = parse_intake_comment(1004, body, self.recorded_ids, set())
        self.assertEqual(disp, "already_recorded")

    def test_duplicate_queue_intake_handling(self):
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload)
        disp, _, _ = parse_intake_comment(1005, body, self.recorded_ids, {"new-run-002"})
        self.assertEqual(disp, "duplicate")

    def test_owner_withdrawn_handling_issue_150(self):
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload)
        disp, _, reason = parse_intake_comment(5088187239, body, self.recorded_ids, set())
        self.assertEqual(disp, "owner_withdrawn")
        self.assertIn("150", reason)

    def test_source_watch_planner_ownership_refusal(self):
        pr_meta = {
            "number": 12,
            "body": "Wrong header\n<!-- ledger-source-watch:v1 -->",
            "is_draft": True,
            "metadata": {"mutable_state": True}
        }
        res = self.planner.plan_pr_action(pr_meta, True, "head123")
        self.assertEqual(res["action"], "REFUSE_AMBIGUOUS_OWNERSHIP")

    def test_source_watch_planner_freeze_refusal(self):
        pr_meta = {
            "number": 12,
            "body": "<!-- ledger-source-watch:v1 -->\n{}",
            "is_draft": True,
            "is_frozen": True,
            "metadata": {"mutable_state": True}
        }
        res = self.planner.plan_pr_action(pr_meta, True, "head123")
        self.assertEqual(res["action"], "REFUSE_FROZEN")

    def test_source_watch_planner_unexpected_head_refusal(self):
        pr_meta = {
            "number": 12,
            "body": "<!-- ledger-source-watch:v1 -->\n{}",
            "is_draft": True,
            "is_frozen": False,
            "metadata": {"mutable_state": True, "expected_head_sha": "expected_sha_999"}
        }
        res = self.planner.plan_pr_action(pr_meta, True, "current_sha_111")
        self.assertEqual(res["action"], "REFUSE_UNEXPECTED_HEAD")

    def test_source_watch_planner_valid_update(self):
        pr_meta = {
            "number": 12,
            "body": "<!-- ledger-source-watch:v1 -->\n{}",
            "is_draft": True,
            "is_frozen": False,
            "metadata": {"mutable_state": True, "expected_head_sha": "head123"}
        }
        res = self.planner.plan_pr_action(pr_meta, True, "head123")
        self.assertEqual(res["action"], "UPDATE_EXISTING_PR")
        self.assertEqual(res["pr_number"], 12)

if __name__ == "__main__":
    unittest.main()
