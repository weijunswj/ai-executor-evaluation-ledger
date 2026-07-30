import copy
import json
import unittest

from scripts.processor.common import AUTHORIZED_PAIRS
from scripts.processor.intake_parser import (
    canonical_record_from_payload,
    parse_intake_comment,
)
from scripts.processor.source_watch import (
    SourceWatchPlanner,
    parse_pr_body,
    validate_metadata,
)


class TestIntakeAndSourceWatch(unittest.TestCase):
    def setUp(self):
        self.valid_payload = {
            "schema_version": 1,
            "record_type": "evaluation_intake",
            "controller_run_id": "controller-a005-001",
            "evaluation_run_id": "run-a005-001",
            "provider": "OpenAI",
            "canonical_base_model": "GPT-5.6 Sol",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "ledger-public",
            "source_revision": "a" * 40,
            "task_class": "repository-repair",
            "difficulty": "high",
            "verdict": "accepted",
            "score_dimensions": {
                "correctness": 5,
                "safety_and_scope_control": 5,
                "evidence_quality": 4,
                "operational_judgement": 5,
                "task_understanding": 5,
                "tracker_and_repository_hygiene": 5,
                "autonomy": 4,
                "efficiency": 4,
            },
            "weighted_score_5": 4.6,
            "public_safe_evidence": {
                "first_pass_accepted": True,
                "controller_intervention_required": False,
                "safe_final_state_reported": True,
                "safe_final_state_verified": True,
                "root_cause_identified": True,
                "root_cause_result": "validated fixture result",
                "follow_up_count": 0,
                "confidence": "verified",
                "verified_strengths": ["bounded change"],
                "verified_defects": [],
                "integrity_and_control_flags": [],
            },
            "secret_exposure_status": "none",
            "reviewed_at": "2026-07-29T10:00:00Z",
        }

    def body(self, payload=None):
        return "<!-- ledger-intake:v1 -->\n" + json.dumps(payload or self.valid_payload)

    def parse(self, payload=None, *, comment_id=1001, recorded=None, seen=None):
        return parse_intake_comment(
            comment_id,
            self.body(payload),
            recorded if recorded is not None else set(),
            seen if seen is not None else set(),
        )

    def test_valid_authorised_pair_is_admitted_without_invented_fields(self):
        disposition, parsed, reason = self.parse()
        self.assertEqual((disposition, reason), ("admitted", "admitted"))
        self.assertNotIn("weighted_score_10", parsed)
        record = canonical_record_from_payload(parsed)
        self.assertEqual(record["revision_binding"], "a" * 40)
        self.assertEqual(record["model"], "GPT-5.6 Sol")

    def test_all_current_authorised_pairs_are_explicit(self):
        self.assertEqual(
            AUTHORIZED_PAIRS,
            frozenset(
                {
                    ("Xiaomi", "MiMo 2.5 Pro"),
                    ("MiMo", "MiMo 2.5 Pro"),
                    ("Anthropic", "Claude Opus 5"),
                    ("DeepSeek", "DeepSeek V4 Pro"),
                    ("OpenAI", "GPT-5.6 Sol"),
                    ("Qwen", "Qwen3.7 Plus"),
                    ("Google", "Gemini 3.1 Pro"),
                    ("MiniMax", "MiniMax M3"),
                }
            ),
        )

    def test_missing_required_authority_is_generic_and_non_mutating(self):
        for field in ("controller_run_id", "evaluation_run_id", "source_revision", "weighted_score_5", "reviewed_at"):
            payload = copy.deepcopy(self.valid_payload)
            payload.pop(field)
            disposition, parsed, reason = self.parse(payload)
            self.assertEqual(disposition, "authority_missing", field)
            self.assertEqual(parsed, {})
            self.assertEqual(reason, "authority_missing")

    def test_unknown_top_level_and_nested_fields_are_closed(self):
        top = copy.deepcopy(self.valid_payload)
        top["unknown_extra_field"] = "fixture-only"
        self.assertEqual(self.parse(top)[0], "invalid_schema")
        nested = copy.deepcopy(self.valid_payload)
        nested["public_safe_evidence"]["unknown_nested_field"] = True
        self.assertEqual(self.parse(nested)[0], "invalid_schema")

    def test_invalid_withdrawn_ineligible_and_unsupported_pairs(self):
        withdrawn = copy.deepcopy(self.valid_payload)
        withdrawn.update(provider="Anthropic", canonical_base_model="Claude Opus 4.8")
        self.assertEqual(self.parse(withdrawn)[0], "withdrawn_identity")
        ineligible = copy.deepcopy(self.valid_payload)
        ineligible.update(provider="Qwen", canonical_base_model="Qwen3.6 Plus")
        self.assertEqual(self.parse(ineligible)[0], "ineligible_identity")
        unsupported = copy.deepcopy(self.valid_payload)
        unsupported.update(provider="Google", canonical_base_model="GPT-5.6 Sol")
        self.assertEqual(self.parse(unsupported)[0], "unsupported_identity")

    def test_reasoning_and_self_grading_identity_are_rejected(self):
        reasoning = copy.deepcopy(self.valid_payload)
        reasoning["public_safe_evidence"]["reasoning" + "_level"] = "high"
        self.assertEqual(self.parse(reasoning)[0], "ineligible_identity")
        self_grading = copy.deepcopy(self.valid_payload)
        self_grading["public_safe_evidence"]["executor_self_grading"] = True
        self.assertEqual(self.parse(self_grading)[0], "ineligible_identity")
        suffixed = copy.deepcopy(self.valid_payload)
        suffixed["canonical_base_model"] = "GPT-5.6 Sol " + "High"
        self.assertEqual(self.parse(suffixed)[0], "unsupported_identity")

    def test_marker_framing_and_exactly_one_json_object(self):
        self.assertEqual(self.parse()[0], "admitted")
        self.assertEqual(parse_intake_comment(2, " prefix" + self.body(), set(), set())[0], "no_marker")
        self.assertEqual(parse_intake_comment(3, self.body() + "\nprose", set(), set())[0], "invalid_schema")
        self.assertEqual(parse_intake_comment(4, self.body() + json.dumps(self.valid_payload), set(), set())[0], "invalid_schema")

    def test_rejected_source_bytes_are_not_returned(self):
        secret = "gh" + "p_" + "A" * 24
        private_path = "C:" + "\\Users\\" + "fixture\\private.txt"
        payload = copy.deepcopy(self.valid_payload)
        payload["task_class"] = secret + " " + private_path
        disposition, parsed, reason = self.parse(payload)
        self.assertEqual(disposition, "unsafe_content")
        self.assertEqual(parsed, {})
        visible = json.dumps({"disposition": disposition, "payload": parsed, "reason": reason})
        self.assertNotIn(secret, visible)
        self.assertNotIn(private_path, visible)

    def test_identity_and_credential_patterns_are_rejected_before_schema(self):
        unsafe_values = (
            "123e4567-e89b-12d3-a456-426614174000",
            "eyJ" + "A" * 12 + "." + "B" * 12 + "." + "C" * 12,
            "https://fixture.invalid/?" + "to" + "ken" + "=" + "A" * 12,
            "to" + "ken" + "=" + '"' + "A" * 12 + '"',
        )
        for unsafe in unsafe_values:
            payload = copy.deepcopy(self.valid_payload)
            payload["task_class"] = unsafe
            disposition, parsed, reason = self.parse(payload)
            self.assertEqual((disposition, parsed, reason), ("unsafe_content", {}, "unsafe_content"))

    def test_duplicate_and_recorded_identities_are_terminal(self):
        self.assertEqual(self.parse(recorded={"run-a005-001"})[0], "already_recorded")
        seen = set()
        first = self.parse(comment_id=10, seen=seen)
        second_payload = copy.deepcopy(self.valid_payload)
        second_payload["evaluation_run_id"] = self.valid_payload["evaluation_run_id"]
        second = self.parse(second_payload, comment_id=11, seen=seen)
        self.assertEqual(first[0], "admitted")
        self.assertEqual(second[0], "duplicate_identity")

    def test_source_watch_requires_closed_metadata_and_triple_fence(self):
        metadata = {
            "schema_version": 1,
            "record_type": "source_watch_pr_metadata",
            "mode": "initial",
            "base_sha": "a" * 40,
            "canonical_main_sha": "b" * 40,
            "batch_id": "batch-a005-001",
            "controller_run_id": "controller-a005-001",
            "pr_number": 151,
            "expected_head_sha": "c" * 40,
            "activation_mode": "dry-run",
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "review_freeze_state": "not_started",
            "dry_run": True,
        }
        body = "<!-- ledger-source-watch:v1 -->\n```json\n" + json.dumps(metadata) + "\n```\nsummary"
        parsed, remainder = parse_pr_body(body)
        validate_metadata(parsed)
        self.assertEqual(remainder, "summary")
        with self.assertRaises(ValueError):
            parse_pr_body(body.replace("```json", "``json"))
        incomplete = dict(metadata)
        incomplete.pop("dry_run")
        with self.assertRaises(ValueError):
            validate_metadata(incomplete)

    def test_source_watch_planner_refuses_frozen_and_moved_state(self):
        planner = SourceWatchPlanner()
        self.assertEqual(planner.plan_pr_action(None, False, "a" * 40)["action"], "NO_WORK")
        self.assertEqual(planner.plan_pr_action(None, True, "a" * 40)["action"], "CREATE_NEW_DRAFT_PR")
        metadata = {
            "schema_version": 1,
            "record_type": "source_watch_pr_metadata",
            "mode": "initial",
            "base_sha": "a" * 40,
            "canonical_main_sha": "b" * 40,
            "batch_id": "batch-a005-001",
            "controller_run_id": "controller-a005-001",
            "pr_number": 151,
            "expected_head_sha": "c" * 40,
            "activation_mode": "dry-run",
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "review_freeze_state": "frozen",
            "dry_run": True,
        }
        pr = {"number": 151, "body": "<!-- ledger-source-watch:v1 -->\n```json\n" + json.dumps(metadata) + "\n```", "is_draft": True}
        self.assertEqual(planner.plan_pr_action(pr, True, "c" * 40)["action"], "REFUSE_FROZEN")
        metadata["review_freeze_state"] = "not_started"
        pr["body"] = "<!-- ledger-source-watch:v1 -->\n```json\n" + json.dumps(metadata) + "\n```"
        self.assertEqual(planner.plan_pr_action(pr, True, "d" * 40)["action"], "REFUSE_UNEXPECTED_HEAD")
        pr["number"] = 152
        self.assertEqual(planner.plan_pr_action(pr, True, "c" * 40)["action"], "REFUSE_AMBIGUOUS_OWNERSHIP")

    def test_source_watch_uses_durable_live_shaped_review_evidence(self):
        planner = SourceWatchPlanner()
        metadata = {
            "schema_version": 1,
            "record_type": "source_watch_pr_metadata",
            "mode": "initial",
            "base_sha": "a" * 40,
            "canonical_main_sha": "a" * 40,
            "batch_id": "batch-a010-001",
            "controller_run_id": "controller-a010-001",
            "pr_number": 151,
            "expected_head_sha": "c" * 40,
            "activation_mode": "dry-run",
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "review_freeze_state": "not_started",
            "dry_run": True,
        }

        def live_pr(meta):
            return {
                "number": 151,
                "body": "<!-- ledger-source-watch:v1 -->\n```json\n"
                + json.dumps(meta)
                + "\n```",
                "is_draft": True,
                "reviews": {"nodes": []},
                "latestReviews": {"nodes": []},
                "reviewThreads": {"nodes": []},
                "controller_review_started": False,
            }

        mutable = live_pr(metadata)
        self.assertEqual(
            planner.plan_pr_action(mutable, True, "c" * 40)["action"],
            "UPDATE_EXISTING_PR",
        )

        frozen_meta = dict(metadata)
        frozen_meta["review_freeze_state"] = "frozen"
        frozen = live_pr(frozen_meta)
        self.assertEqual(
            planner.plan_pr_action(frozen, True, "c" * 40)["action"],
            "REFUSE_FROZEN",
        )
        self.assertEqual(
            planner.plan_pr_action(frozen, True, "d" * 40)["reason"],
            "frozen_head_mismatch",
        )

        missing = dict(metadata)
        missing.pop("review_freeze_state")
        reviewed = live_pr(missing)
        reviewed["reviews"]["nodes"] = [{"state": "COMMENTED"}]
        self.assertEqual(
            planner.plan_pr_action(reviewed, True, "c" * 40)["reason"],
            "review_freeze_missing",
        )

        conflicting = live_pr(metadata)
        conflicting["reviewThreads"]["nodes"] = [{"isResolved": False}]
        self.assertEqual(
            planner.plan_pr_action(conflicting, True, "c" * 40)["reason"],
            "review_freeze_conflict",
        )

        ambiguous = live_pr(metadata)
        ambiguous["reviews"] = {"unexpected": []}
        self.assertEqual(
            planner.plan_pr_action(ambiguous, True, "c" * 40)["action"],
            "REFUSE_AMBIGUOUS_OWNERSHIP",
        )


if __name__ == "__main__":
    unittest.main()
