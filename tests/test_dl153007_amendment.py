from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from scripts import check_public_safety as public_safety
from scripts import rebuild_views
from scripts import refreeze_frozen_batch
from scripts.processor import batch_processor, cleanup_workflow, frozen_replay
from scripts.processor.common import (
    ProcessorError,
    canonical_json_bytes,
    safe_author_hash,
    safe_comment_body_hash,
)
from scripts.processor.frozen_source import refetch_frozen_source
from scripts.processor.intake_parser import (
    canonical_record_from_payload,
    parse_intake_comment,
)


ROOT = Path(__file__).resolve().parents[1]
LOCKED_BASE = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
RECEIPT_PATH = (
    ROOT
    / "ledger"
    / "receipts"
    / "batches"
    / "batch-20260729-gate3-amendment-004.json"
)
LOGIN_FIELD = "l" + "ogin"


def valid_payload(run_id: str = "run-dl153007-fixture") -> dict:
    dimensions = {
        "correctness": 5,
        "safety_and_scope_control": 4,
        "evidence_quality": 3,
        "operational_judgement": 2,
        "task_understanding": 1,
        "tracker_and_repository_hygiene": 5,
        "autonomy": 4,
        "efficiency": 3,
    }
    return {
        "schema_version": 1,
        "record_type": "evaluation_intake",
        "controller_run_id": "controller-dl153007-fixture",
        "evaluation_run_id": run_id,
        "provider": "OpenAI",
        "canonical_base_model": "GPT-5.6 Sol",
        "evaluation_protocol": "gated_v1",
        "repository_alias": "ledger-public",
        "source_revision": "a" * 40,
        "task_class": "repository-repair",
        "difficulty": "high",
        "verdict": "accepted",
        "score_dimensions": dimensions,
        "weighted_score_5": 3.5,
        "weighted_score_10": 7,
        "public_safe_evidence": {
            "first_pass_accepted": True,
            "controller_intervention_required": False,
            "safe_final_state_reported": True,
            "safe_final_state_verified": True,
            "root_cause_identified": True,
            "root_cause_result": "bounded fixture",
            "follow_up_count": 0,
            "confidence": "verified",
            "verified_strengths": ["bounded evidence"],
            "verified_defects": [],
            "integrity_and_control_flags": [],
        },
        "secret_exposure_status": "none",
        "reviewed_at": "2026-08-04T00:00:00Z",
    }


def intake_body(payload: dict) -> str:
    return "<!-- ledger-intake:v1 -->\n" + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


class TestA1FutureAppendOnlyBases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_bytes = (ROOT / "evaluations.jsonl").read_bytes()
        cls.sample = next(
            json.loads(line)
            for line in cls.base_bytes.decode("utf-8").splitlines()
            if line.strip() and json.loads(line).get("record_type") == "evaluation"
        )

    def _candidate_line(self, suffix: str) -> bytes:
        record = copy.deepcopy(self.sample)
        record["run_id"] = f"run-dl153007-append-{suffix}"
        return (
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    def _verify(self, candidate: bytes) -> None:
        with tempfile.TemporaryDirectory(prefix="dl153007-append-") as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture" + "@" + "example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"],
                cwd=root,
                check=True,
            )
            ledger = root / "evaluations.jsonl"
            ledger.write_bytes(self.base_bytes)
            subprocess.run(["git", "add", "evaluations.jsonl"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            ledger.write_bytes(candidate)
            with mock.patch.object(rebuild_views, "ROOT", root), mock.patch.object(
                rebuild_views,
                "LEDGER_PATH",
                ledger,
            ):
                rebuild_views.verify_append_only(base_sha)

    def test_locked_one_time_migration_path_still_passes(self):
        rebuild_views.verify_append_only(LOCKED_BASE)

    def test_future_base_accepts_no_change_one_append_and_multiple_appends(self):
        for label, candidate in {
            "unchanged": self.base_bytes,
            "one": self.base_bytes + self._candidate_line("one"),
            "multiple": self.base_bytes
            + self._candidate_line("one")
            + self._candidate_line("two"),
        }.items():
            with self.subTest(label=label):
                self._verify(candidate)

    def test_future_base_rejects_preserved_prefix_mutation(self):
        lines = self.base_bytes.splitlines(keepends=True)
        inserted = self._candidate_line("inserted")
        cases = {
            "edited": lines[0].replace(b'"schema_version":2', b'"schema_version":1')
            + b"".join(lines[1:]),
            "deleted": b"".join(lines[1:]),
            "reordered": lines[1] + lines[0] + b"".join(lines[2:]),
            "inserted": lines[0] + inserted + b"".join(lines[1:]),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                self._verify(candidate)

    def test_future_base_rejects_malformed_appended_jsonl(self):
        valid = self._candidate_line("valid").decode("utf-8")
        duplicate_nested = valid.replace(
            '"scores":{',
            '"scores":{"correctness":5,"correctness":5,',
            1,
        ).encode("utf-8")
        duplicate_id = self.base_bytes.splitlines(keepends=True)[0]
        cases = {
            "malformed_utf8": self.base_bytes + b"\xff\n",
            "duplicate_keys": self.base_bytes + duplicate_nested,
            "nonfinite": self.base_bytes + b'{"run_id":"run-nonfinite","score":NaN}\n',
            "duplicate_run_id": self.base_bytes + duplicate_id,
            "non_object": self.base_bytes + b"[]\n",
            "incomplete_record": self.base_bytes + self._candidate_line("partial").rstrip(b"\n"),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                self._verify(candidate)


class TestA2StandaloneUuidScanning(unittest.TestCase):
    @staticmethod
    def uuid(lower: bool = True) -> str:
        value = "123e4567" + "-e89b-12d3-a456-" + "426614174000"
        return value if lower else value.upper()

    def test_uuid_is_rejected_in_prose_and_innocuous_json_value(self):
        for label, text in {
            "prose": "run " + self.uuid(),
            "innocuous_json": json.dumps({"harmless": self.uuid()}),
        }.items():
            with self.subTest(label=label):
                self.assertTrue(public_safety.scan_text("fixture", text))

    def test_uuid_is_rejected_in_sensitive_assignment_and_case_variants(self):
        cases = (
            json.dumps({"owner_id": self.uuid()}),
            "prefix " + self.uuid(lower=False),
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(public_safety.scan_text("fixture", text))

    def test_safe_non_uuid_and_canonical_run_identifier_pass(self):
        for text in ("123e4567-not-a-uuid", "2026-08-04-ledger-amendment-038"):
            with self.subTest(text=text):
                self.assertFalse(public_safety.scan_text("fixture", text))


class TestA3EffectiveReviewerState(unittest.TestCase):
    def review(self, review_id: int, reviewer_id: int, state: str, submitted: str, login: str = "reviewer") -> dict:
        return {
            "id": review_id,
            "user": {"id": reviewer_id, "login": login},
            "state": state,
            "submitted_at": submitted,
        }

    def state(self, reviews: list[dict]) -> str:
        helper = getattr(cleanup_workflow, "_effective_review_state")
        return helper(reviews)

    def test_changes_requested_then_approved_is_clear(self):
        reviews = [
            self.review(1, 10, "CHANGES_REQUESTED", "2026-08-04T00:00:00Z"),
            self.review(2, 10, "APPROVED", "2026-08-04T00:01:00Z"),
        ]
        self.assertEqual(self.state(reviews), "clear")

    def test_approved_then_changes_requested_is_blocking(self):
        reviews = [
            self.review(1, 10, "APPROVED", "2026-08-04T00:00:00Z"),
            self.review(2, 10, "CHANGES_REQUESTED", "2026-08-04T00:01:00Z"),
        ]
        self.assertEqual(self.state(reviews), "blocking")

    def test_commented_does_not_erase_decisive_state(self):
        reviews = [
            self.review(1, 10, "CHANGES_REQUESTED", "2026-08-04T00:00:00Z"),
            self.review(2, 10, "COMMENTED", "2026-08-04T00:01:00Z"),
        ]
        self.assertEqual(self.state(reviews), "blocking")

    def test_multiple_reviewers_use_each_effective_state(self):
        reviews = [
            self.review(1, 10, "CHANGES_REQUESTED", "2026-08-04T00:00:00Z", "first"),
            self.review(2, 10, "APPROVED", "2026-08-04T00:01:00Z", "first"),
            self.review(3, 20, "APPROVED", "2026-08-04T00:00:00Z", "second"),
            self.review(4, 20, "CHANGES_REQUESTED", "2026-08-04T00:02:00Z", "second"),
        ]
        self.assertEqual(self.state(reviews), "blocking")

    def test_duplicate_ambiguous_missing_and_malformed_reviews_fail_closed(self):
        valid = self.review(1, 10, "APPROVED", "2026-08-04T00:00:00Z")
        cases = {
            "duplicate_review_id": [valid, copy.deepcopy(valid)],
            "identity_ambiguity": [
                valid,
                self.review(2, 10, "APPROVED", "2026-08-04T00:01:00Z", "changed"),
            ],
            "login_ambiguity": [
                valid,
                self.review(2, 11, "APPROVED", "2026-08-04T00:01:00Z"),
            ],
            "missing_identity": [{key: value for key, value in valid.items() if key != "user"}],
            "malformed_state": [{**valid, "state": "UNKNOWN"}],
            "malformed_timestamp": [{**valid, "submitted_at": "not-a-time"}],
            "noncanonical_state": [{**valid, "state": "approved"}],
        }
        for label, reviews in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.state(reviews)

    def test_pending_review_remains_blocking(self):
        self.assertEqual(
            self.state([self.review(1, 10, "PENDING", None)]),
            "blocking",
        )


class FrozenRefreezeFixture(unittest.TestCase):
    def authority(self) -> tuple[dict, list[dict], str]:
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        comments = []
        bindings = []
        hashes = {}
        fingerprints = []
        for index, comment_id in enumerate(receipt["source_comment_ids"]):
            created = f"2026-07-29T10:{index // 60:02d}:{index % 60:02d}Z"
            body = f"fixture-body-{comment_id}"
            body_hash = safe_comment_body_hash(body)
            comment = {
                "id": comment_id,
                "user": {LOGIN_FIELD: "fixture-author"},
                "body": body,
                "created_at": created,
                "updated_at": created,
            }
            comments.append(comment)
            hashes[str(comment_id)] = body_hash
            bindings.append(
                {
                    "comment_id": comment_id,
                    "created_at": created,
                    "updated_at": created,
                    "body_sha256": body_hash,
                }
            )
            fingerprints.append(
                {
                    "id": comment_id,
                    "author_sha256": safe_author_hash("fixture-author"),
                    "created_at": created,
                    "updated_at": created,
                    "body_sha256": body_hash,
                }
            )
        snapshot = hashlib.sha256(canonical_json_bytes(fingerprints)).hexdigest()
        receipt["source_body_sha256"] = hashes
        receipt["comment_bindings"] = bindings
        receipt["queue_snapshot_sha256"] = snapshot
        return receipt, comments, snapshot

    def precompare(self, receipt: dict, comments: list[dict], snapshot: str) -> dict:
        helper = getattr(
            __import__("scripts.processor.frozen_source", fromlist=["refetch_frozen_source_for_refreeze"]),
            "refetch_frozen_source_for_refreeze",
        )
        with mock.patch.object(frozen_replay, "FROZEN_SNAPSHOT_SHA256", snapshot):
            return helper(
                ROOT,
                receipt,
                queue_fetcher=lambda _root: copy.deepcopy(comments),
            )


class TestA4ReachableRefreeze(FrozenRefreezeFixture):
    def changed(self) -> tuple[dict, list[dict], str]:
        receipt, comments, snapshot = self.authority()
        comments[0]["body"] += "-corrected"
        comments[0]["updated_at"] = "2026-07-29T12:00:00Z"
        return receipt, comments, snapshot

    def test_exactly_one_valid_body_correction_is_detected(self):
        receipt, comments, snapshot = self.changed()
        evidence = self.precompare(receipt, comments, snapshot)
        self.assertEqual(evidence["changed_comment_ids"], [comments[0]["id"]])

    def test_zero_two_membership_author_and_time_changes_fail_closed(self):
        cases = {}
        receipt, comments, snapshot = self.authority()
        cases["zero"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        comments[1]["body"] += "-second"
        comments[1]["updated_at"] = "2026-07-29T12:00:01Z"
        cases["two"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        occupied = {comment["id"] for comment in comments}
        added_id = next(
            value
            for value in range(comments[0]["id"], receipt["source_comment_watermark"])
            if value not in occupied
        )
        comments.append(copy.deepcopy(comments[-1]) | {"id": added_id})
        cases["added"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        cases["removed"] = (receipt, comments[1:], snapshot)
        receipt, comments, snapshot = self.changed()
        comments[1]["user"]["login"] = "different-author"
        cases["author"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        comments[1]["created_at"] = "2026-07-29T12:00:00Z"
        cases["created"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        comments[0]["updated_at"] = "2026-07-28T12:00:00Z"
        cases["regressed"] = (receipt, comments, snapshot)
        receipt, comments, snapshot = self.changed()
        comments[0]["updated_at"] = "malformed"
        cases["malformed"] = (receipt, comments, snapshot)
        for label, values in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.precompare(*values)

    def test_later_comments_remain_outside_the_frozen_membership(self):
        receipt, comments, snapshot = self.changed()
        comments.append(
            copy.deepcopy(comments[-1]) | {"id": receipt["source_comment_watermark"] + 1}
        )
        evidence = self.precompare(receipt, comments, snapshot)
        self.assertEqual(evidence["later_comment_count"], 1)

    def test_replacement_marker_payload_and_run_identity_are_revalidated(self):
        helper = getattr(refreeze_frozen_batch, "canonical_refreeze_replacement")
        payload = valid_payload("run-refreeze-fixture")
        record = helper(intake_body(payload), payload["evaluation_run_id"])
        self.assertEqual(record["run_id"], payload["evaluation_run_id"])
        cases = (
            (json.dumps(payload), payload["evaluation_run_id"]),
            ("<!-- ledger-intake:v1 -->\n{} trailing", payload["evaluation_run_id"]),
            (intake_body(payload), "different-run"),
        )
        for body, expected in cases:
            with self.subTest(body=body[:20]), self.assertRaises(ProcessorError):
                helper(body, expected)

    def test_normal_frozen_replay_remains_strict(self):
        receipt, comments, snapshot = self.authority()
        with mock.patch.object(frozen_replay, "FROZEN_SNAPSHOT_SHA256", snapshot):
            refetch_frozen_source(
                ROOT,
                receipt,
                queue_fetcher=lambda _root: copy.deepcopy(comments),
            )
            comments[0]["body"] += "-changed"
            with self.assertRaises(ProcessorError):
                refetch_frozen_source(
                    ROOT,
                    receipt,
                    queue_fetcher=lambda _root: copy.deepcopy(comments),
                )


class TestA5MalformedPagination(unittest.TestCase):
    def call(self, value, path: str = "fixture"):
        with mock.patch.object(cleanup_workflow, "gh_json", return_value=value):
            return cleanup_workflow._gh_get_paginated(path, ROOT)

    def test_valid_empty_and_multiple_pages(self):
        self.assertEqual(self.call([[], []]), [])
        self.assertEqual(self.call([[{"id": 1}], [{"id": 2}]]), [{"id": 1}, {"id": 2}])

    def test_malformed_outer_page_elements_and_mixed_pages_fail_closed(self):
        cases = {
            "outer": {},
            "page": [[{"id": 1}], {}],
            "element": [[{"id": 1}, "bad"]],
            "mixed": [[{"id": 1}], [{"id": 2}, None]],
        }
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError) as raised:
                self.call(value)
            self.assertEqual(raised.exception.code, "processor_failure")

    def test_malformed_reviews_and_receipt_evidence_fail_closed(self):
        for path in (
            "repos/weijunswj/ai-executor-evaluation-ledger/pulls/151/reviews?per_page=100",
            "repos/weijunswj/ai-executor-evaluation-ledger/issues/143/comments?per_page=100",
        ):
            with self.subTest(path=path), self.assertRaises(ProcessorError):
                self.call([[{"id": 1}, []]], path)


class TestA6IncrementalOwnerAuthority(unittest.TestCase):
    def comment(self, *, numeric_id: int, author_name: str, association: str = "OWNER", body: str | None = None) -> dict:
        return {
            "id": 9001,
            "user": {"id": numeric_id, LOGIN_FIELD: author_name},
            "author_association": association,
            "body": body if body is not None else intake_body(valid_payload()),
            "created_at": "2026-08-04T00:00:00Z",
            "updated_at": "2026-08-04T00:00:00Z",
        }

    def parse(self, comment: dict, owner: dict):
        helper = getattr(batch_processor, "_parse_authorized_intake_comment")
        return helper(comment, owner, set(), set())

    def test_authoritative_owner_is_admitted_and_non_owner_is_rejected(self):
        owner = {"id": 7001, LOGIN_FIELD: "owner-fixture"}
        admitted = self.parse(self.comment(numeric_id=7001, author_name="owner-fixture"), owner)
        self.assertEqual(admitted[0], "admitted")
        rejected = self.parse(self.comment(numeric_id=7002, author_name="other-fixture", association="NONE"), owner)
        self.assertEqual(rejected, ("authority_missing", {}, "authority_missing"))

    def test_forged_association_and_partial_identity_matches_are_rejected(self):
        owner = {"id": 7001, LOGIN_FIELD: "owner-fixture"}
        cases = (
            self.comment(numeric_id=7002, author_name="other-fixture", association="OWNER"),
            self.comment(numeric_id=7002, author_name="owner-fixture"),
            self.comment(numeric_id=7001, author_name="other-fixture"),
        )
        for comment in cases:
            with self.subTest(comment=comment["user"]):
                self.assertEqual(self.parse(comment, owner)[0], "authority_missing")

    def test_comment_identity_movement_between_fetches_fails_closed(self):
        first = self.comment(numeric_id=7001, author_name="owner-fixture")
        moved = copy.deepcopy(first)
        moved["user"]["id"] = 7002
        with self.assertRaises(ProcessorError):
            batch_processor._verify_selected_comment(first, moved)

    def test_ordinary_comments_keep_existing_disposition_and_identity_is_not_emitted(self):
        owner = {"id": 7001, LOGIN_FIELD: "owner-fixture"}
        ordinary = self.comment(
            numeric_id=7002,
            author_name="other-fixture",
            association="NONE",
            body="ordinary retained comment",
        )
        result = self.parse(ordinary, owner)
        self.assertEqual(result, ("no_marker", {}, "no_marker"))
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(str(owner["id"]), encoded)
        self.assertNotIn(owner[LOGIN_FIELD], encoded)


class TestA7DerivedWeightedScores(unittest.TestCase):
    def derive(self, dimensions: dict) -> Decimal:
        helper = getattr(
            __import__("scripts.processor.intake_parser", fromlist=["derive_weighted_score_5"]),
            "derive_weighted_score_5",
        )
        return helper(dimensions)

    def test_zero_five_mixed_decimal_boundary_and_float_edge_scores(self):
        fields = tuple(valid_payload()["score_dimensions"])
        cases = {
            "zero": ({field: 0 for field in fields}, Decimal("0")),
            "five": ({field: 5 for field in fields}, Decimal("5")),
            "mixed": (valid_payload()["score_dimensions"], Decimal("3.5")),
            "decimal": ({field: Decimal("2.5") for field in fields}, Decimal("2.5")),
            "lower_boundary": ({field: 0.1 for field in fields}, Decimal("0.1")),
            "upper_boundary": ({field: 4.9 for field in fields}, Decimal("4.9")),
            "float_edge": ({field: 0.1 + 0.2 for field in fields}, Decimal(str(0.1 + 0.2))),
        }
        for label, (dimensions, expected) in cases.items():
            with self.subTest(label=label):
                self.assertEqual(self.derive(dimensions), expected)

    def test_correct_supplied_five_and_ten_totals_are_admitted_and_derived(self):
        payload = valid_payload()
        code, parsed, _ = parse_intake_comment(9001, intake_body(payload), set(), set())
        self.assertEqual(code, "admitted")
        record = canonical_record_from_payload(parsed)
        self.assertEqual(Decimal(str(record["weighted_score_5"])), Decimal("3.5"))
        self.assertEqual(Decimal(str(record["weighted_score_10"])), Decimal("7"))

    def test_incorrect_supplied_five_or_ten_total_is_rejected(self):
        wrong_five = valid_payload()
        wrong_five["weighted_score_5"] = 3.6
        wrong_ten = valid_payload()
        wrong_ten["weighted_score_10"] = 7.1
        for payload in (wrong_five, wrong_ten):
            with self.subTest(payload=payload):
                self.assertEqual(
                    parse_intake_comment(9001, intake_body(payload), set(), set())[0],
                    "invalid_schema",
                )

    def test_frozen_canonical_files_remain_byte_for_byte_unchanged(self):
        paths = (
            ROOT / "evaluations.jsonl",
            ROOT / "ledger" / "dispositions.jsonl",
            ROOT / "README.md",
            ROOT / "scorecard.md",
            ROOT / "analysis" / "model-recommendation.json",
        )
        before = {path: path.read_bytes() for path in paths}
        self.derive(valid_payload()["score_dimensions"])
        self.assertEqual(before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
