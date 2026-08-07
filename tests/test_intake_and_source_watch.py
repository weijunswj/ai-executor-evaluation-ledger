import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from scripts.processor.common import (
    AUTHORIZED_PAIRS,
    FROZEN_BATCH_ID,
    FROZEN_SNAPSHOT_SHA256,
    REASONING_KEYS,
    safe_comment_body_hash,
)
from scripts.processor import intake_parser
from scripts.processor.intake_parser import (
    HistoricalReviewTimestampAuthority,
    canonical_record_from_payload,
    parse_intake_comment,
)
from scripts.processor.source_watch import (
    SourceWatchPlanner,
    normalize_native_review_evidence,
    parse_pr_body,
    validate_metadata,
)


class TestIntakeAndSourceWatch(unittest.TestCase):
    def setUp(self):
        self.valid_payload = {
            "schema_version": 2,
            "record_type": "evaluation_intake",
            "controller_run_id": "controller-a005-001",
            "evaluation_run_id": "run-a005-001",
            "provider": "OpenAI",
            "canonical_base_model": "GPT-5.6 Sol",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "ledger-public",
            "revision_assertion": "private_revision_verified",
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
            "weighted_score_5": 4.75,
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
        return "<!-- ledger-intake:v2 -->\n" + json.dumps(payload or self.valid_payload)

    def historical_body(self, payload=None, *, include_source_revision=True):
        value = copy.deepcopy(payload or self.valid_payload)
        value["schema_version"] = 1
        value.pop("revision_assertion", None)
        if include_source_revision:
            value["source_revision"] = "a" * 40
        return "<!-- ledger-intake:v1 -->\n" + json.dumps(value)

    def parse(self, payload=None, *, comment_id=1001, recorded=None, seen=None):
        return parse_intake_comment(
            comment_id,
            self.body(payload),
            recorded if recorded is not None else set(),
            seen if seen is not None else set(),
        )

    def _frozen_authority(self, body, *, comment_id=None, **overrides):
        receipt = json.loads(
            Path(
                "ledger/receipts/batches/"
                "batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        frozen_ids = frozenset(receipt["source_comment_ids"])
        values = {
            "batch_id": FROZEN_BATCH_ID,
            "comment_id": (
                receipt["source_comment_ids"][0]
                if comment_id is None
                else comment_id
            ),
            "frozen_comment_ids": frozen_ids,
            "verified_snapshot_sha256": FROZEN_SNAPSHOT_SHA256,
            "source_body_sha256": safe_comment_body_hash(body),
            "expected_body_sha256": safe_comment_body_hash(body),
            "source_created_at": "2026-07-29T10:00:00Z",
            "expected_created_at": "2026-07-29T10:00:00Z",
            "source_updated_at": "2026-07-29T10:00:00Z",
            "expected_updated_at": "2026-07-29T10:00:00Z",
        }
        values.update(overrides)
        return HistoricalReviewTimestampAuthority(**values)

    def test_valid_authorised_pair_is_admitted_without_invented_fields(self):
        disposition, parsed, reason = self.parse()
        self.assertEqual((disposition, reason), ("admitted", "admitted"))
        self.assertNotIn("weighted_score_10", parsed)
        record = canonical_record_from_payload(parsed)
        self.assertEqual(record["revision_binding"], "private_revision_verified")
        self.assertEqual(record["model"], "GPT-5.6 Sol")

    def test_forward_intake_uses_closed_revision_assertion(self):
        payload = copy.deepcopy(self.valid_payload)
        payload["schema_version"] = 2
        payload["revision_assertion"] = "private_revision_verified"
        disposition, parsed, reason = parse_intake_comment(
            1002,
            "<!-- ledger-intake:v2 -->\n" + json.dumps(payload),
            set(),
            set(),
        )
        self.assertEqual((disposition, reason), ("admitted", "admitted"))
        record = canonical_record_from_payload(parsed)
        self.assertEqual(record["revision_binding"], "private_revision_verified")
        self.assertNotIn("source_revision", record)

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
        for field in ("controller_run_id", "evaluation_run_id", "revision_assertion", "weighted_score_5", "reviewed_at"):
            payload = copy.deepcopy(self.valid_payload)
            payload.pop(field)
            disposition, parsed, reason = self.parse(payload)
            self.assertEqual(disposition, "authority_missing", field)
            self.assertEqual(parsed, {})
            self.assertEqual(reason, "authority_missing")

    def test_closed_frozen_timestamp_authority_repairs_only_reviewed_at(self):
        receipt = json.loads(
            Path(
                "ledger/receipts/batches/"
                "batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        comment_id = receipt["source_comment_ids"][0]
        frozen_ids = frozenset(receipt["source_comment_ids"])
        created_at = "2026-07-29T10:00:00Z"
        payload = copy.deepcopy(self.valid_payload)
        payload.pop("reviewed_at")
        body = self.historical_body(payload)
        body_hash = safe_comment_body_hash(body)
        authority = HistoricalReviewTimestampAuthority(
            batch_id=FROZEN_BATCH_ID,
            comment_id=comment_id,
            frozen_comment_ids=frozen_ids,
            verified_snapshot_sha256=FROZEN_SNAPSHOT_SHA256,
            source_body_sha256=body_hash,
            expected_body_sha256=body_hash,
            source_created_at=created_at,
            expected_created_at=created_at,
            source_updated_at=created_at,
            expected_updated_at=created_at,
        )
        code, adapted, _reason = parse_intake_comment(
            comment_id,
            body,
            set(),
            set(),
            historical_review_authority=authority,
        )
        self.assertEqual(code, "admitted")
        self.assertEqual(adapted["reviewed_at"], created_at)

        missing_other = copy.deepcopy(payload)
        self.assertEqual(
            parse_intake_comment(
                comment_id,
                self.historical_body(missing_other, include_source_revision=False),
                set(),
                set(),
                historical_review_authority=authority,
            )[0],
            "authority_missing",
        )
        malformed = copy.deepcopy(authority.__dict__)
        malformed["source_created_at"] = "not-a-date"
        malformed["expected_created_at"] = "not-a-date"
        self.assertEqual(
            parse_intake_comment(
                comment_id,
                body,
                set(),
                set(),
                historical_review_authority=HistoricalReviewTimestampAuthority(
                    **malformed
                ),
            )[0],
            "authority_missing",
        )

    def test_frozen_timestamp_authority_never_replaces_body_value(self):
        receipt = json.loads(
            Path(
                "ledger/receipts/batches/"
                "batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        comment_id = receipt["source_comment_ids"][0]
        body = self.historical_body()
        body_hash = safe_comment_body_hash(body)
        authority = HistoricalReviewTimestampAuthority(
            batch_id=FROZEN_BATCH_ID,
            comment_id=comment_id,
            frozen_comment_ids=frozenset(receipt["source_comment_ids"]),
            verified_snapshot_sha256=FROZEN_SNAPSHOT_SHA256,
            source_body_sha256=body_hash,
            expected_body_sha256=body_hash,
            source_created_at="2026-07-29T11:00:00Z",
            expected_created_at="2026-07-29T11:00:00Z",
            source_updated_at="2026-07-29T11:00:00Z",
            expected_updated_at="2026-07-29T11:00:00Z",
        )
        code, adapted, _reason = parse_intake_comment(
            comment_id,
            body,
            set(),
            set(),
            historical_review_authority=authority,
        )
        self.assertEqual(code, "admitted")
        self.assertEqual(
            adapted["reviewed_at"],
            self.valid_payload["reviewed_at"],
        )

    def test_historical_timestamp_authority_rejects_frozen_scope_mismatches(self):
        payload = copy.deepcopy(self.valid_payload)
        payload.pop("reviewed_at")
        body = self.historical_body(payload)
        receipt = json.loads(
            Path(
                "ledger/receipts/batches/"
                "batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        nonmember_id = max(receipt["source_comment_ids"]) + 1
        baseline = self._frozen_authority(body)
        mismatches = {
            "different_batch": {
                "batch_id": FROZEN_BATCH_ID + "-future",
            },
            "comment_outside_frozen_membership": {
                "comment_id": nonmember_id,
            },
            "snapshot_hash": {"verified_snapshot_sha256": "0" * 64},
            "source_body_hash": {"source_body_sha256": "0" * 64},
            "expected_body_hash": {"expected_body_sha256": "1" * 64},
            "created_at": {
                "expected_created_at": "2026-07-29T10:01:00Z",
            },
            "updated_at": {
                "expected_updated_at": "2026-07-29T10:01:00Z",
            },
            "malformed_created_at": {
                "source_created_at": "not-a-date",
                "expected_created_at": "not-a-date",
            },
        }
        for label, changes in mismatches.items():
            with self.subTest(label=label):
                code, parsed, reason = parse_intake_comment(
                    baseline.comment_id,
                    body,
                    set(),
                    set(),
                    historical_review_authority=replace(baseline, **changes),
                )
                self.assertEqual(
                    (code, parsed, reason),
                    ("authority_missing", {}, "authority_missing"),
                )

    def test_historical_timestamp_authority_uses_created_at_only(self):
        payload = copy.deepcopy(self.valid_payload)
        payload.pop("reviewed_at")
        body = self.historical_body(payload)
        authority = self._frozen_authority(
            body,
            source_created_at="2026-07-29T12:00:00Z",
            expected_created_at="2026-07-29T12:00:00Z",
            source_updated_at="2026-07-29T13:00:00Z",
            expected_updated_at="2026-07-29T13:00:00Z",
        )
        code, adapted, reason = parse_intake_comment(
            authority.comment_id,
            body,
            set(),
            set(),
            historical_review_authority=authority,
        )
        self.assertEqual((code, reason), ("admitted", "admitted"))
        self.assertEqual(adapted["reviewed_at"], "2026-07-29T12:00:00Z")

    def test_historical_timestamp_parser_does_not_consult_clock_or_local_artifacts(self):
        payload = copy.deepcopy(self.valid_payload)
        payload.pop("reviewed_at")
        body = self.historical_body(payload)
        authority = self._frozen_authority(body)

        class FailIfAccessed:
            def __getattr__(self, name):
                raise AssertionError("unexpected external source access")

        with mock.patch.object(
            intake_parser,
            "time",
            FailIfAccessed(),
            create=True,
        ), mock.patch.object(
            intake_parser,
            "datetime",
            FailIfAccessed(),
            create=True,
        ), mock.patch.object(
            intake_parser.Path,
            "read_text",
            side_effect=AssertionError("unexpected local text read"),
        ), mock.patch.object(
            intake_parser.Path,
            "read_bytes",
            side_effect=AssertionError("unexpected local byte read"),
        ), mock.patch.object(
            intake_parser.Path,
            "open",
            side_effect=AssertionError("unexpected local file open"),
        ):
            code, adapted, reason = parse_intake_comment(
                authority.comment_id,
                body,
                {"fixture-existing-evaluation"},
                set(),
                historical_review_authority=authority,
            )

        self.assertEqual((code, reason), ("admitted", "admitted"))
        self.assertEqual(adapted["reviewed_at"], "2026-07-29T10:00:00Z")

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
        inference_key = next(
            key for key in REASONING_KEYS if key.startswith("requested")
        )
        reasoning["public_safe_evidence"][inference_key] = "high"
        self.assertEqual(self.parse(reasoning)[0], "ineligible_identity")
        self_grading = copy.deepcopy(self.valid_payload)
        self_grading["public_safe_evidence"]["executor_self_grading"] = True
        self.assertEqual(self.parse(self_grading)[0], "ineligible_identity")
        suffixed = copy.deepcopy(self.valid_payload)
        suffixed["canonical_base_model"] = (
            self.valid_payload["canonical_base_model"] + " " + "High"
        )
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
            "123e4567" + "-e89b-12d3-a456-" + "426614174000",
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

    def test_duplicate_intake_keys_fail_closed_before_adaptation(self):
        compact = json.dumps(self.valid_payload, separators=(",", ":"))
        cases = {
            "provider_identical": compact[:-1] + ',"provider":"OpenAI","provider":"OpenAI"}',
            "provider_conflicting": compact[:-1] + ',"provider":"OpenAI","provider":"Qwen"}',
            "model_alias": compact[:-1] + ',"model":"GPT-5.6 Sol","model":"Qwen3.7 Plus"}',
            "verdict": compact[:-1] + ',"verdict":"accepted","verdict":"hold"}',
            "nested_score": compact.replace(
                '"score_dimensions":{"correctness":5,',
                '"score_dimensions":{"correctness":5,"correctness":5,',
                1,
            ),
            "nested_evidence": compact.replace(
                '"public_safe_evidence":{"first_pass_accepted":true,',
                '"public_safe_evidence":{"first_pass_accepted":true,"first_pass_accepted":false,',
                1,
            ),
            "nested_multiple": (
                compact.replace(
                    '"score_dimensions":{"correctness":5,',
                    '"score_dimensions":{"correctness":5,"correctness":5,',
                    1,
                ).replace(
                    '"public_safe_evidence":{"first_pass_accepted":true,',
                    '"public_safe_evidence":{"first_pass_accepted":true,"first_pass_accepted":false,',
                    1,
                )
            ),
            "historical_alias": compact[:-1] + ',"base_model":"GPT-5.6 Sol","base_model":"Qwen3.7 Plus"}',
            "nonfinite_combination": compact[:-1] + ',"provider":NaN}',
            "trailing_json": compact + " trailing",
        }
        for label, raw in cases.items():
            with self.subTest(label=label):
                result = parse_intake_comment(
                    1001,
                    "<!-- ledger-intake:v2 -->\n" + raw,
                    set(),
                    set(),
                )
                self.assertEqual(result, ("invalid_schema", {}, "invalid_schema"))

    def test_source_watch_duplicate_metadata_keys_fail_closed(self):
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
            "dry_run": True,
        }
        compact = json.dumps(metadata, separators=(",", ":"))
        cases = {
            "activation_mode": compact[:-1] + ',"activation_mode":"dry-run","activation_mode":"live"}',
            "dry_run": compact[:-1] + ',"dry_run":true,"dry_run":false}',
            "base_sha": compact[:-1] + ',"base_sha":"' + "a" * 40 + '","base_sha":"' + "b" * 40 + '"}',
            "canonical_main_sha": compact[:-1] + ',"canonical_main_sha":"' + "b" * 40 + '","canonical_main_sha":"' + "a" * 40 + '"}',
            "expected_head_sha": compact[:-1] + ',"expected_head_sha":"' + "c" * 40 + '","expected_head_sha":"' + "d" * 40 + '"}',
            "nonfinite_combination": compact[:-1] + ',"dry_run":NaN}',
            "trailing_json": compact + " trailing",
        }
        for label, raw in cases.items():
            with self.subTest(label=label):
                body = (
                    "<!-- ledger-source-watch:v1 -->\n```json\n"
                    + raw
                    + "\n```\nsummary"
                )
                with self.assertRaises(ValueError) as raised:
                    parse_pr_body(body)
                self.assertEqual(str(raised.exception), "invalid_source_watch_envelope")


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

        def complete_connection(nodes=None):
            nodes = list(nodes or [])
            return {
                "nodes": nodes,
                "pageInfo": {
                    "hasNextPage": False,
                    "hasPreviousPage": False,
                    "startCursor": None,
                    "endCursor": None,
                },
                "totalCount": len(nodes),
            }

        def live_pr(meta):
            return {
                "number": 151,
                "body": "<!-- ledger-source-watch:v1 -->\n```json\n"
                + json.dumps(meta)
                + "\n```",
                "is_draft": True,
                "reviews": complete_connection(),
                "latestReviews": complete_connection(),
                "reviewThreads": complete_connection(),
                "controller_review_started": False,
            }

        mutable = live_pr(metadata)
        self.assertEqual(
            set(normalize_native_review_evidence(mutable)),
            {"reviews", "latestReviews", "reviewThreads"},
        )
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
        reviewed["reviews"] = complete_connection([{"state": "COMMENTED"}])
        self.assertEqual(
            planner.plan_pr_action(reviewed, True, "c" * 40)["reason"],
            "review_freeze_missing",
        )

        conflicting = live_pr(metadata)
        conflicting["reviewThreads"] = complete_connection(
            [{"isResolved": False}]
        )
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

        for field in ("reviews", "latestReviews", "reviewThreads"):
            omitted = live_pr(metadata)
            omitted.pop(field)
            self.assertEqual(
                planner.plan_pr_action(omitted, True, "c" * 40)["reason"],
                "ambiguous_review_state",
            )
            null_connection = live_pr(metadata)
            null_connection[field] = None
            self.assertEqual(
                planner.plan_pr_action(
                    null_connection,
                    True,
                    "c" * 40,
                )["reason"],
                "ambiguous_review_state",
            )

        missing_page_info = live_pr(metadata)
        missing_page_info["reviews"] = {"nodes": [], "totalCount": 0}
        self.assertEqual(
            planner.plan_pr_action(
                missing_page_info,
                True,
                "c" * 40,
            )["reason"],
            "ambiguous_review_state",
        )

        has_next_page = live_pr(metadata)
        has_next_page["reviews"]["pageInfo"]["hasNextPage"] = True
        self.assertEqual(
            planner.plan_pr_action(has_next_page, True, "c" * 40)["reason"],
            "ambiguous_review_state",
        )

        malformed_page_info = live_pr(metadata)
        malformed_page_info["reviews"]["pageInfo"]["hasNextPage"] = "false"
        self.assertEqual(
            planner.plan_pr_action(
                malformed_page_info,
                True,
                "c" * 40,
            )["reason"],
            "ambiguous_review_state",
        )

        string_cursor = live_pr(metadata)
        string_cursor["reviews"]["pageInfo"]["endCursor"] = "cursor-1"
        self.assertEqual(
            planner.plan_pr_action(
                string_cursor,
                True,
                "c" * 40,
            )["action"],
            "UPDATE_EXISTING_PR",
        )

        malformed_cursor = live_pr(metadata)
        malformed_cursor["reviews"]["pageInfo"]["endCursor"] = 1
        self.assertEqual(
            planner.plan_pr_action(
                malformed_cursor,
                True,
                "c" * 40,
            )["reason"],
            "ambiguous_review_state",
        )

        unknown_page_info = live_pr(metadata)
        unknown_page_info["reviews"]["pageInfo"]["unavailable"] = True
        self.assertEqual(
            planner.plan_pr_action(
                unknown_page_info,
                True,
                "c" * 40,
            )["reason"],
            "ambiguous_review_state",
        )

        unavailable = live_pr(metadata)
        unavailable["reviews"]["unavailable"] = True
        self.assertEqual(
            planner.plan_pr_action(unavailable, True, "c" * 40)["reason"],
            "ambiguous_review_state",
        )

        incomplete_aggregation = live_pr(metadata)
        incomplete_aggregation["reviews"]["totalCount"] = 1
        self.assertEqual(
            planner.plan_pr_action(
                incomplete_aggregation,
                True,
                "c" * 40,
            )["reason"],
            "ambiguous_review_state",
        )

        legacy_list = live_pr(metadata)
        legacy_list["reviews"] = []
        self.assertEqual(
            planner.plan_pr_action(legacy_list, True, "c" * 40)["reason"],
            "ambiguous_review_state",
        )

        caller_conflict = live_pr(metadata)
        caller_conflict["reviews"] = complete_connection(
            [{"state": "COMMENTED"}]
        )
        caller_conflict["controller_review_started"] = False
        self.assertEqual(
            planner.plan_pr_action(
                caller_conflict,
                True,
                "c" * 40,
            )["reason"],
            "review_freeze_conflict",
        )

        boolean_only_conflict = live_pr(metadata)
        boolean_only_conflict["controller_review_started"] = True
        self.assertEqual(
            planner.plan_pr_action(
                boolean_only_conflict,
                True,
                "c" * 40,
            )["reason"],
            "review_freeze_conflict",
        )

    def test_native_graphql_fixtures_flow_through_normalizer_and_planner(self):
        fixtures = json.loads(
            Path(
                "tests/fixtures/source_watch/"
                "native_review_evidence.json"
            ).read_text(encoding="utf-8")
        )
        planner = SourceWatchPlanner()
        empty = fixtures["mutable_empty"]
        active = fixtures["active_nonempty"]

        for connection_name in ("reviews", "latestReviews", "reviewThreads"):
            self.assertIsNone(
                empty[connection_name]["pageInfo"]["startCursor"]
            )
            self.assertIsNone(
                empty[connection_name]["pageInfo"]["endCursor"]
            )
            self.assertIsInstance(
                empty[connection_name]["pageInfo"]["hasPreviousPage"],
                bool,
            )
            self.assertIsInstance(
                active[connection_name]["pageInfo"]["hasPreviousPage"],
                bool,
            )
            self.assertIsInstance(
                active[connection_name]["pageInfo"]["startCursor"],
                str,
            )
            self.assertIsInstance(
                active[connection_name]["pageInfo"]["endCursor"],
                str,
            )

        empty_normalized = normalize_native_review_evidence(empty)
        self.assertEqual(
            empty_normalized,
            {"reviews": [], "latestReviews": [], "reviewThreads": []},
        )
        self.assertEqual(
            planner.plan_pr_action(empty, True, "c" * 40)["action"],
            "UPDATE_EXISTING_PR",
        )
        active_normalized = normalize_native_review_evidence(active)
        self.assertEqual(
            {field: len(nodes) for field, nodes in active_normalized.items()},
            {"reviews": 1, "latestReviews": 1, "reviewThreads": 1},
        )
        self.assertEqual(
            planner.plan_pr_action(active, True, "c" * 40)["reason"],
            "review_freeze_conflict",
        )

        def assert_rejected(label, mutate):
            candidate = copy.deepcopy(empty)
            mutate(candidate)
            with self.subTest(label=label):
                self.assertIsNone(normalize_native_review_evidence(candidate))
                self.assertEqual(
                    planner.plan_pr_action(candidate, True, "c" * 40)["reason"],
                    "ambiguous_review_state",
                )

        assert_rejected(
            "has_next_page",
            lambda candidate: candidate["reviews"]["pageInfo"].update(
                hasNextPage=True
            ),
        )
        assert_rejected(
            "total_count_mismatch",
            lambda candidate: candidate["reviews"].update(totalCount=1),
        )
        assert_rejected(
            "boolean_total_count",
            lambda candidate: candidate["reviews"].update(totalCount=True),
        )
        for field in ("reviews", "latestReviews", "reviewThreads"):
            assert_rejected(
                "missing_" + field,
                lambda candidate, field=field: candidate.pop(field),
            )
            assert_rejected(
                "null_" + field,
                lambda candidate, field=field: candidate.update({field: None}),
            )
        assert_rejected(
            "missing_page_info",
            lambda candidate: candidate["reviews"].pop("pageInfo"),
        )
        assert_rejected(
            "missing_has_next_page",
            lambda candidate: candidate["reviews"]["pageInfo"].pop(
                "hasNextPage"
            ),
        )
        assert_rejected(
            "missing_nodes",
            lambda candidate: candidate["reviews"].pop("nodes"),
        )
        assert_rejected(
            "missing_total_count",
            lambda candidate: candidate["reviews"].pop("totalCount"),
        )
        assert_rejected(
            "malformed_page_info",
            lambda candidate: candidate["reviews"].update(pageInfo=None),
        )
        assert_rejected(
            "malformed_has_next_page",
            lambda candidate: candidate["reviews"]["pageInfo"].update(
                hasNextPage="false"
            ),
        )
        assert_rejected(
            "unknown_page_info_field",
            lambda candidate: candidate["reviews"]["pageInfo"].update(
                unavailable=True
            ),
        )
        assert_rejected(
            "unknown_connection_field",
            lambda candidate: candidate["reviews"].update(
                unexpected=True
            ),
        )
        for label in ("partial", "error", "unavailable"):
            assert_rejected(
                label + "_connection",
                lambda candidate, label=label: candidate["reviews"].update(
                    {label: True} if label != "error" else {"errors": [{"message": "fixture"}]}
                ),
            )

        frozen = copy.deepcopy(empty)
        metadata, remainder = parse_pr_body(frozen["body"])
        metadata["review_freeze_state"] = "frozen"
        frozen["body"] = (
            SourceWatchPlanner.OWNERSHIP_MARKER
            + "\n```json\n"
            + json.dumps(metadata)
            + "\n```\n"
            + remainder
        )
        self.assertEqual(
            planner.plan_pr_action(frozen, True, "c" * 40),
            {"action": "REFUSE_FROZEN", "reason": "review_freeze"},
        )
        self.assertEqual(
            planner.plan_pr_action(frozen, True, "d" * 40),
            {"action": "REFUSE_FROZEN", "reason": "frozen_head_mismatch"},
        )

    def test_native_graphql_page_info_omissions_preserve_fixture_results(self):
        fixtures = json.loads(
            Path(
                "tests/fixtures/source_watch/"
                "native_review_evidence.json"
            ).read_text(encoding="utf-8")
        )
        planner = SourceWatchPlanner()
        connection_names = ("reviews", "latestReviews", "reviewThreads")
        optional_page_info_fields = (
            "hasPreviousPage",
            "startCursor",
            "endCursor",
        )
        fixture_expectations = {
            "mutable_empty": {
                "normalized": {
                    "reviews": [],
                    "latestReviews": [],
                    "reviewThreads": [],
                },
                "plan": {
                    "action": "UPDATE_EXISTING_PR",
                    "pr_number": 151,
                    "reason": "safe_mutable_source_watch_pr",
                },
            },
            "active_nonempty": {
                "normalized": {
                    "reviews": [{"state": "COMMENTED"}],
                    "latestReviews": [{"state": "COMMENTED"}],
                    "reviewThreads": [{"isResolved": False}],
                },
                "plan": {
                    "action": "REFUSE_FROZEN",
                    "reason": "review_freeze_conflict",
                },
            },
        }

        for fixture_name, expected in fixture_expectations.items():
            baseline = copy.deepcopy(fixtures[fixture_name])
            self.assertEqual(
                normalize_native_review_evidence(baseline),
                expected["normalized"],
            )
            self.assertEqual(
                planner.plan_pr_action(baseline, True, "c" * 40),
                expected["plan"],
            )
            for connection_name in connection_names:
                for page_info_field in optional_page_info_fields:
                    candidate = copy.deepcopy(baseline)
                    candidate[connection_name]["pageInfo"].pop(page_info_field)
                    with self.subTest(
                        fixture=fixture_name,
                        connection=connection_name,
                        page_info_field=page_info_field,
                    ):
                        self.assertEqual(
                            normalize_native_review_evidence(candidate),
                            expected["normalized"],
                        )
                        self.assertEqual(
                            planner.plan_pr_action(candidate, True, "c" * 40),
                            expected["plan"],
                        )

        combined = copy.deepcopy(fixtures["active_nonempty"])
        for connection_name in connection_names:
            for page_info_field in optional_page_info_fields:
                combined[connection_name]["pageInfo"].pop(page_info_field)
            self.assertEqual(
                set(combined[connection_name]),
                {"nodes", "pageInfo", "totalCount"},
            )
            self.assertEqual(
                set(combined[connection_name]["pageInfo"]),
                {"hasNextPage"},
            )
            self.assertFalse(
                combined[connection_name]["pageInfo"]["hasNextPage"]
            )
            self.assertEqual(
                combined[connection_name]["totalCount"],
                len(combined[connection_name]["nodes"]),
            )
        self.assertEqual(
            normalize_native_review_evidence(combined),
            fixture_expectations["active_nonempty"]["normalized"],
        )
        self.assertEqual(
            planner.plan_pr_action(combined, True, "c" * 40),
            fixture_expectations["active_nonempty"]["plan"],
        )


if __name__ == "__main__":
    unittest.main()
