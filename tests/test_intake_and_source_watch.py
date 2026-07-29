import unittest
import json
from scripts.processor.intake_parser import parse_intake_comment, ALLOWED_PAIRS

class TestIntakeAndSourceWatch(unittest.TestCase):
    def setUp(self):
        self.valid_payload = {
            "schema_version": 1,
            "record_type": "evaluation_intake",
            "controller_run_id": "2026-07-29-controller-001",
            "evaluation_run_id": "2026-07-29-gemini-3-6-flash-run-001",
            "provider": "Google",
            "canonical_base_model": "Gemini 3.6 Flash",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "ai-executor-evaluation-ledger",
            "source_revision": "rev-123",
            "task_class": "research",
            "difficulty": "medium",
            "verdict": "accepted",
            "score_dimensions": {
                "correctness": 4.8,
                "safety_and_scope_control": 5.0,
                "evidence_quality": 4.5,
                "operational_judgement": 4.8,
                "task_understanding": 4.8,
                "tracker_and_repository_hygiene": 5.0,
                "autonomy": 4.8,
                "efficiency": 4.8
            },
            "weighted_score_5": 4.81,
            "public_safe_evidence": {
                "first_pass_accepted": True,
                "controller_intervention_required": False,
                "confidence": "baseline"
            },
            "secret_exposure_status": "none"
        }

    def test_admitted_valid_intake(self):
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload)
        disp, payload, reason = parse_intake_comment(1001, body, set(), set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(payload["evaluation_run_id"], "2026-07-29-gemini-3-6-flash-run-001")

    def test_uuid_run_id_admitted(self):
        payload = dict(self.valid_payload)
        payload["evaluation_run_id"] = "37f16751-1fba-4b23-900a-8cd7a645d9ef"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1002, body, set(), set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(parsed["evaluation_run_id"], "37f16751-1fba-4b23-900a-8cd7a645d9ef")

    def test_prohibited_uuid_placement_rejected(self):
        payload = dict(self.valid_payload)
        payload["owner"] = "37f16751-1fba-4b23-900a-8cd7a645d9ef"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1003, body, set(), set())
        self.assertEqual(disp, "prohibited_identity")
        self.assertIn("Prohibited identity field", reason)

    def test_gemini_3_1_pro_and_minimax_m3_admission(self):
        for provider, model in [("Google", "Gemini 3.1 Pro"), ("MiniMax", "MiniMax M3")]:
            payload = dict(self.valid_payload)
            payload["provider"] = provider
            payload["canonical_base_model"] = model
            payload["evaluation_run_id"] = f"run-{provider.lower()}-{model.lower().replace(' ', '-')}"
            body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
            disp, parsed, reason = parse_intake_comment(1004, body, set(), set())
            self.assertEqual(disp, "admitted", f"Failed for {provider}/{model}: {reason}")

    def test_unknown_model_pair_blocks(self):
        payload = dict(self.valid_payload)
        payload["provider"] = "UnknownProvider"
        payload["canonical_base_model"] = "UnknownModel"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1005, body, set(), set())
        self.assertEqual(disp, "pending_controller_action")

    def test_optional_issue_and_pr_numbers(self):
        payload = dict(self.valid_payload)
        payload["issue_number"] = 142
        payload["pull_request_number"] = 151
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1006, body, set(), set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(parsed["issue_number"], 142)

    def test_unknown_field_rejection(self):
        payload = dict(self.valid_payload)
        payload["unknown_extra_field"] = "bad"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1007, body, set(), set())
        self.assertEqual(disp, "pending_controller_action")

    def test_reasoning_keys_rejection(self):
        payload = dict(self.valid_payload)
        payload["thinking_setting"] = "High"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1008, body, set(), set())
        self.assertEqual(disp, "ineligible")
        self.assertIn("prohibited reasoning metadata", reason)

    def test_extraneous_prose_rejection(self):
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(self.valid_payload) + "\nExtra trailing prose"
        disp, parsed, reason = parse_intake_comment(1009, body, set(), set())
        self.assertEqual(disp, "invalid_json")
        self.assertIn("Extraneous prose", reason)

    def test_verdicts_accepted_amend_hold_fail(self):
        for v in ["accepted", "amend", "hold", "fail"]:
            payload = dict(self.valid_payload)
            payload["verdict"] = v
            body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
            disp, parsed, reason = parse_intake_comment(1010, body, set(), set())
            self.assertEqual(disp, "admitted", f"Verdict {v} failed: {reason}")
            self.assertEqual(parsed["verdict"], v)

    def test_strong_confidence_supported(self):
        payload = dict(self.valid_payload)
        payload["public_safe_evidence"]["confidence"] = "strong"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1011, body, set(), set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(parsed["public_safe_evidence"]["confidence"], "strong")

    def test_historical_intake_adapter_success(self):
        payload = {
            "run_id": "historical-run-001",
            "model": "Claude Opus 4.8",
            "provider": "Anthropic",
            "gate_disposition": "amend",
            "revision_binding": "commit-abc1234",
            "subject_alias": "ai-executor-evaluation-ledger",
            "task_class": "research",
            "difficulty": "medium",
            "score": {
                "correctness": 4.5
            },
            "evidence": {
                "root_cause_identified": True,
                "follow_up_runs_required": 1,
                "confidence": "strong"
            }
        }
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1012, body, set(), set())
        self.assertEqual(disp, "admitted")
        self.assertEqual(parsed["evaluation_run_id"], "historical-run-001")
        self.assertEqual(parsed["canonical_base_model"], "Claude Opus 4.8")
        self.assertEqual(parsed["verdict"], "amend")
        self.assertEqual(parsed["source_revision"], "commit-abc1234")
        self.assertEqual(parsed["public_safe_evidence"]["root_cause_result"], "identified")
        self.assertEqual(parsed["public_safe_evidence"]["follow_up_count"], 1)

    def test_ambiguous_legacy_shape_remains_pending(self):
        payload = {
            "run_id": "legacy-ambiguous-001",
            "model": "Claude Opus 4.8",
            "provider": "Anthropic",
            "verdict": "accepted"
        }
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1013, body, set(), set())
        self.assertEqual(disp, "pending_controller_action")

    def test_blocked_controller_action_not_terminal(self):
        payload = dict(self.valid_payload)
        payload["verdict"] = "blocked"
        body = "<!-- ledger-intake:v1 -->\n" + json.dumps(payload)
        disp, parsed, reason = parse_intake_comment(1014, body, set(), set())
        self.assertEqual(disp, "pending_controller_action")

    def test_wrong_frozen_expected_head_metadata_fails_ci(self):
        from scripts.processor.source_watch import SourceWatchPlanner
        planner = SourceWatchPlanner()
        pr_meta = {
            "number": 151,
            "is_draft": True,
            "is_frozen": False,
            "body": "<!-- ledger-source-watch:v1 -->",
            "metadata": {
                "mutable_state": True,
                "review_freeze_state": False,
                "expected_head_sha": "wrong_head_sha_123"
            }
        }
        res = planner.plan_pr_action(pr_meta, has_pending_work=True, current_head_sha="actual_head_sha_456")
        self.assertEqual(res["action"], "REFUSE_UNEXPECTED_HEAD")

if __name__ == "__main__":
    unittest.main()
