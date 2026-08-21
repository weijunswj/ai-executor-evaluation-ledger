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
    canonical_json_line_bytes,
    safe_author_hash,
    safe_comment_body_hash,
)
from scripts.processor.frozen_source import refetch_frozen_source
from scripts.processor.intake_parser import (
    HISTORICAL_INTAKE_VALIDATOR,
    INTAKE_VALIDATOR,
    adapt_historical_payload,
    canonical_record_from_payload,
    parse_intake_comment,
)


ROOT = Path(__file__).resolve().parents[1]
# Durable canonical ancestor carrying the locked first-59 evaluation bytes.
CANONICAL_FIRST_59_BASE = "d54fb99da162f49ccb616a8756725b9aea83ac1d"
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
        "schema_version": 2,
        "record_type": "evaluation_intake",
        "controller_run_id": "controller-dl153007-fixture",
        "evaluation_run_id": run_id,
        "provider": "OpenAI",
        "canonical_base_model": "GPT-5.6 Sol",
        "evaluation_protocol": "gated_v1",
        "repository_alias": "ledger-public",
        "revision_assertion": "private_revision_verified",
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
    return "<!-- ledger-intake:v2 -->\n" + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def historical_intake_body(payload: dict) -> str:
    value = copy.deepcopy(payload)
    value["schema_version"] = 1
    value.pop("revision_assertion", None)
    value["source_revision"] = "a" * 40
    return "<!-- ledger-intake:v1 -->\n" + json.dumps(
        value,
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

    def _verify(self, candidate: bytes, *, base_bytes: bytes | None = None) -> None:
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
            ledger.write_bytes(self.base_bytes if base_bytes is None else base_bytes)
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
        historical_prefix = subprocess.run(
            ["git", "show", f"{CANONICAL_FIRST_59_BASE}:evaluations.jsonl"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            "387dfc1347189555ef91eabf767e62738f777b2e80b79f5378e95170df40cb64",
            hashlib.sha256(historical_prefix).hexdigest(),
        )
        self.assertTrue(self.base_bytes.startswith(historical_prefix))
        self._verify(self.base_bytes, base_bytes=historical_prefix)

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

    def test_changed_historical_v1_uses_historical_validator(self):
        receipt, comments, _snapshot = self.authority()
        payload = valid_payload("run-refreeze-validator")
        body = historical_intake_body(payload)
        raw_payload = json.loads(body.split("\n", 1)[1])
        adapted = adapt_historical_payload(raw_payload)
        self.assertTrue(tuple(INTAKE_VALIDATOR.iter_errors(adapted)))
        self.assertFalse(tuple(HISTORICAL_INTAKE_VALIDATOR.iter_errors(adapted)))

        changed_comments = copy.deepcopy(comments)
        changed_comments[0]["body"] = body
        changed_comments[0]["updated_at"] = "2026-07-29T12:00:00Z"
        first_id = str(changed_comments[0]["id"])
        receipt["terminal_outcomes"][first_id] = {
            "outcome_code": "admitted",
            "evaluation_run_id": payload["evaluation_run_id"],
        }
        evidence = {
            "source_body_sha256": {
                str(comment["id"]): safe_comment_body_hash(comment["body"])
                for comment in changed_comments
            },
            "comments": changed_comments,
            "fingerprints": [{"id": comment["id"]} for comment in changed_comments],
            "later_comment_count": 0,
        }
        replacement = refreeze_frozen_batch.canonical_refreeze_replacement(
            body,
            payload["evaluation_run_id"],
        )
        with tempfile.TemporaryDirectory(prefix="dl153007-refreeze-validator-") as raw:
            root = Path(raw)
            receipt_path = (
                root
                / "ledger"
                / "receipts"
                / "batches"
                / "batch-20260729-gate3-amendment-004.json"
            )
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            (root / "evaluations.jsonl").write_bytes(
                canonical_json_line_bytes(replacement)
            )
            dispositions = root / "ledger" / "dispositions.jsonl"
            dispositions.parent.mkdir(parents=True, exist_ok=True)
            dispositions.write_bytes(b"")
            with mock.patch.object(
                refreeze_frozen_batch,
                "refetch_frozen_source_for_refreeze",
                return_value=evidence,
            ):
                result = refreeze_frozen_batch.refreeze(root)
            self.assertEqual(result["changed_comment_count"], 1)
            self.assertEqual(result["changed_record_count"], 1)
            self.assertEqual(
                json.loads((root / "evaluations.jsonl").read_text(encoding="utf-8"))["run_id"],
                payload["evaluation_run_id"],
            )

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
        record = helper(
            historical_intake_body(payload),
            payload["evaluation_run_id"],
        )
        self.assertEqual(record["run_id"], payload["evaluation_run_id"])
        cases = (
            (json.dumps(payload), payload["evaluation_run_id"]),
            ("<!-- ledger-intake:v1 -->\n{} trailing", payload["evaluation_run_id"]),
            (historical_intake_body(payload), "different-run"),
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


class TestA8ReceiptCommentEvidenceBoundary(unittest.TestCase):
    ISSUE_URL = cleanup_workflow.RECEIPT_ISSUE_ENDPOINT

    @staticmethod
    def config(recorded_receipt_status: str) -> cleanup_workflow.CleanupConfig:
        return cleanup_workflow.CleanupConfig(
            batch_id="batch-cleanup-live-a005",
            canonical_merge_sha="a" * 40,
            canonical_main_sha="a" * 40,
            expected_head_sha="b" * 40,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="unreviewed",
            pr_state="closed",
            merge_state="merged",
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status=recorded_receipt_status,
            repository_root=Path(tempfile.gettempdir()),
        )

    def matching_value(self) -> dict:
        config = self.config("present_matching")
        return {
            "receipt_type": "cleanup",
            "cleanup_status": "verified",
            "batch_id": config.batch_id,
            "canonical_merge_sha": config.canonical_merge_sha,
            "canonical_main_sha": config.canonical_main_sha,
            "expected_head_sha": config.expected_head_sha,
            "pr_number": config.pr_number,
            "source_issue_number": config.source_issue_number,
            "receipt_issue_number": config.receipt_issue_number,
            "canonical_hashes": {
                key: "a" * 64 for key in cleanup_workflow.CANONICAL_PATHS
            },
            "source_retention_verified": True,
            "recorded_receipt_status": "absent",
            "branch_cleanup_eligible": True,
            "branch_cleanup_reason": "eligible",
            "publication_status": "published",
            "platform_limitation_code": "none",
            "batch_receipt_sha256": "b" * 64,
            "batch_receipt_bytes_sha256": "c" * 64,
            "batch_receipt_blob_sha": "d" * 40,
            "queue_snapshot_sha256": "e" * 64,
            "source_comment_count": 0,
            "admitted_record_count": 0,
        }

    def matching_comment(self, comment_id: int = 81) -> dict:
        return {
            "id": comment_id,
            "issue_url": self.ISSUE_URL,
            "body": cleanup_workflow.RECORDED_MARKER + "\nfixture",
        }

    def status(self, comments: list[dict]) -> str:
        with (
            mock.patch.object(
                cleanup_workflow,
                "_parse_recorded_receipt_body",
                return_value=self.matching_value(),
            ),
            mock.patch.object(
                cleanup_workflow,
                "_receipt_matches_authority",
                return_value=True,
            ),
        ):
            return cleanup_workflow._recorded_receipt_status(
                self.config("absent"), comments
            )

    def prepare(self, comments: list[dict]) -> dict:
        status = self.status(comments)
        config = self.config(status)
        canonical_hashes = {
            key: "1" * 64 for key in cleanup_workflow.CANONICAL_PATHS
        }
        batch = {
            "admitted_run_ids": [],
            "canonical_hashes": canonical_hashes,
            "canonical_record_hashes": {},
            "accepted_record_proofs": {},
            "source_comment_ids": [],
            "source_body_sha256": {},
        }
        authority = {
            field: getattr(config, field)
            for field in (
                "pr_state",
                "merge_state",
                "checks_state",
                "review_state",
                "canonical_merge_sha",
                "expected_head_sha",
                "canonical_main_sha",
                "recorded_receipt_status",
            )
        }
        with (
            mock.patch.object(cleanup_workflow, "_verify_local_canonical_checkout"),
            mock.patch.object(
                cleanup_workflow,
                "_load_batch",
                return_value=(batch, b"{}", "2" * 64),
            ),
            mock.patch.object(cleanup_workflow, "validate_batch_receipt_object"),
            mock.patch.object(cleanup_workflow, "_verify_raw_head_receipt_seal"),
            mock.patch.object(cleanup_workflow, "_git_object_bytes", return_value=b""),
            mock.patch.object(
                cleanup_workflow, "_current_hashes", return_value=canonical_hashes
            ),
            mock.patch.object(cleanup_workflow, "_record_hashes", return_value={}),
            mock.patch.object(
                cleanup_workflow, "_record_identity_proofs", return_value={}
            ),
            mock.patch.object(
                cleanup_workflow,
                "_retained_comment_evidence",
                return_value=([], True),
            ),
        ):
            return cleanup_workflow.prepare_cleanup_receipt(
                config, authority_reader=lambda _config: authority
            )

    def publish(self, direct_issue_url: str, comments_factory) -> dict:
        receipt = {
            "cleanup_status": "verified",
            "recorded_receipt_status": "absent",
            "receipt_issue_number": 143,
        }
        bodies: list[str] = []

        def publisher(body: str) -> int:
            bodies.append(body)
            return 81

        def readback(locator: int) -> dict:
            return {
                "id": locator,
                "issue_url": direct_issue_url,
                "body": bodies[0],
            }

        with mock.patch.object(
            cleanup_workflow,
            "_parse_recorded_receipt_body",
            return_value=dict(receipt),
        ):
            return cleanup_workflow.publish_cleanup_receipt(
                receipt,
                activation_mode="reviewed-live",
                operator_intent="reviewed",
                publisher=publisher,
                readback=readback,
                comments_reader=lambda: comments_factory(bodies[0]),
                authority_verifier=lambda value: value == receipt,
            )

    def test_generic_pagination_still_flattens_dictionary_only_pages(self):
        with mock.patch.object(cleanup_workflow, "gh_json", return_value=[[{}]]):
            self.assertEqual(
                cleanup_workflow._gh_get_paginated("fixture", ROOT),
                [{}],
            )

    def test_valid_status_universes_remain_supported(self):
        independently_built_endpoint = "".join(
            (
                "https://api.",
                "github.com/repos/",
                "weijunswj/",
                "ai-executor-evaluation-ledger/",
                "issues/143",
            )
        )
        self.assertEqual(self.ISSUE_URL, independently_built_endpoint)
        self.assertEqual(self.status([]), "absent")
        for body in ("", "ordinary non-marker comment"):
            with self.subTest(body=body):
                self.assertEqual(
                    self.status(
                        [{"id": 80, "issue_url": self.ISSUE_URL, "body": body}]
                    ),
                    "absent",
                )
        self.assertEqual(self.status([self.matching_comment()]), "present_matching")
        conflicting = self.matching_value() | {"canonical_main_sha": "c" * 40}
        with mock.patch.object(
            cleanup_workflow,
            "_parse_recorded_receipt_body",
            return_value=conflicting,
        ):
            self.assertEqual(
                cleanup_workflow._recorded_receipt_status(
                    self.config("absent"), [self.matching_comment()]
                ),
                "conflicting",
            )

    def test_missing_and_invalid_stable_ids_fail_closed(self):
        invalid_ids = (None, True, False, 0, -1, "81", 81.0, {}, [])
        missing = {"issue_url": self.ISSUE_URL, "body": "ordinary"}
        with self.subTest(value="missing"), self.assertRaises(ProcessorError):
            self.status([missing])
        for value in invalid_ids:
            with self.subTest(value=value), self.assertRaises(ProcessorError):
                self.status(
                    [{"id": value, "issue_url": self.ISSUE_URL, "body": "ordinary"}]
                )

    def test_duplicate_ids_within_and_across_pages_fail_closed(self):
        first = {"id": 81, "issue_url": self.ISSUE_URL, "body": "first"}
        second = {"id": 81, "issue_url": self.ISSUE_URL, "body": "second"}
        with self.assertRaises(ProcessorError):
            self.status([first, second])
        with mock.patch.object(
            cleanup_workflow, "gh_json", return_value=[[first], [second]]
        ):
            comments = cleanup_workflow._gh_get_paginated("fixture", ROOT)
        with self.assertRaises(ProcessorError):
            self.status(comments)

    def test_missing_malformed_and_lookalike_issue_urls_fail_closed(self):
        invalid_urls = (
            None,
            True,
            143,
            {},
            [],
            self.ISSUE_URL.replace("weijunswj/", "other/"),
            self.ISSUE_URL.replace("ai-executor-evaluation-ledger/", "other/"),
            self.ISSUE_URL[:-3] + "142",
            self.ISSUE_URL.replace("api.github.com", "example.test"),
            self.ISSUE_URL.replace("https://", "http://", 1),
            self.ISSUE_URL + "/extra",
            self.ISSUE_URL + "?issue=143",
            self.ISSUE_URL + "#fragment",
            "prefix-" + self.ISSUE_URL,
            self.ISSUE_URL + "-suffix",
            self.ISSUE_URL.replace("api.github.com", "API.github.com"),
            self.ISSUE_URL[:-3] + "%31%34%33",
        )
        missing = {"id": 81, "body": "ordinary"}
        with self.subTest(value="missing"), self.assertRaises(ProcessorError):
            self.status([missing])
        for value in invalid_urls:
            with self.subTest(value=value), self.assertRaises(ProcessorError):
                self.status([{"id": 81, "issue_url": value, "body": "ordinary"}])

    def test_missing_null_and_non_string_bodies_fail_closed(self):
        missing = {"id": 81, "issue_url": self.ISSUE_URL}
        with self.subTest(value="missing"), self.assertRaises(ProcessorError):
            self.status([missing])
        for value in (None, True, False, 0, 1.5, {}, []):
            with self.subTest(value=value), self.assertRaises(ProcessorError):
                self.status([{"id": 81, "issue_url": self.ISSUE_URL, "body": value}])

    def test_malformed_comment_cannot_become_absent(self):
        with self.assertRaises(ProcessorError):
            self.status([{}])

    def test_malformed_comment_cannot_preserve_verified_preparation(self):
        with self.assertRaises(ProcessorError):
            self.prepare([{}])

    def test_malformed_comment_cannot_preserve_branch_eligibility(self):
        with self.assertRaises(ProcessorError):
            self.prepare([{}, self.matching_comment()])

    def test_live_authority_rejects_malformed_receipt_comment_universe(self):
        config = self.config("absent")
        pr = {
            "state": "closed",
            "merged_at": "2026-08-05T00:00:00Z",
            "merge_commit_sha": config.canonical_main_sha,
            "head": {"sha": config.expected_head_sha},
        }
        main = {"object": {"sha": config.canonical_main_sha}}
        raw_commit = {"parents": [], "files": []}
        raw_receipt = {
            "type": "file",
            "encoding": "base64",
            "content": "e30=",
        }
        with (
            mock.patch.object(
                cleanup_workflow,
                "_gh_get_json",
                side_effect=[pr, main, raw_commit, raw_receipt, {"workflow_runs": []}],
            ),
            mock.patch.object(
                cleanup_workflow,
                "_gh_get_paginated",
                side_effect=[[], [{}]],
            ),
            mock.patch.object(cleanup_workflow, "_gh_get_threads", return_value=[]),
            self.assertRaises(ProcessorError),
        ):
            cleanup_workflow._readback_live_authority(config)

    def test_malformed_universe_cannot_publish(self):
        result = self.publish(
            self.ISSUE_URL,
            lambda body: [
                {"id": 81, "issue_url": self.ISSUE_URL, "body": body},
                {},
            ],
        )
        self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")

    def test_duplicate_ids_cannot_hide_behind_body_filtering(self):
        result = self.publish(
            self.ISSUE_URL,
            lambda body: [
                {"id": 81, "issue_url": self.ISSUE_URL, "body": body},
                {"id": 81, "issue_url": self.ISSUE_URL, "body": "ordinary"},
            ],
        )
        self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")

    def test_duplicate_matching_bodies_with_distinct_ids_cannot_publish(self):
        result = self.publish(
            self.ISSUE_URL,
            lambda body: [
                {"id": 81, "issue_url": self.ISSUE_URL, "body": body},
                {"id": 82, "issue_url": self.ISSUE_URL, "body": body},
            ],
        )
        self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")

    def test_valid_canonical_publication_readback_succeeds(self):
        result = self.publish(
            self.ISSUE_URL,
            lambda body: [
                {"id": 81, "issue_url": self.ISSUE_URL, "body": body}
            ],
        )
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["comment_id"], 81)

    def test_pending_operator_behaviour_without_complete_adapters_is_unchanged(self):
        receipt = {
            "cleanup_status": "verified",
            "recorded_receipt_status": "absent",
            "receipt_issue_number": 143,
        }
        without_publisher = cleanup_workflow.publish_cleanup_receipt(
            receipt,
            activation_mode="reviewed-live",
            operator_intent="reviewed",
        )
        self.assertEqual(
            without_publisher["platform_limitation_code"],
            "web_orchestrator_publication_required",
        )
        without_readback = cleanup_workflow.publish_cleanup_receipt(
            receipt,
            activation_mode="reviewed-live",
            operator_intent="reviewed",
            publisher=lambda _body: 81,
        )
        self.assertEqual(
            without_readback["platform_limitation_code"],
            "publication_readback_required",
        )

    def test_wrong_repository_or_issue_cannot_enter_publication_universe(self):
        for issue_url in (
            self.ISSUE_URL.replace("weijunswj/", "example/").replace(
                "ai-executor-evaluation-ledger/", "ledger/"
            ),
            self.ISSUE_URL[:-3] + "142",
        ):
            with self.subTest(issue_url=issue_url):
                result = self.publish(
                    self.ISSUE_URL,
                    lambda body, value=issue_url: [
                        {"id": 81, "issue_url": self.ISSUE_URL, "body": body},
                        {"id": 82, "issue_url": value, "body": "ordinary"},
                    ],
                )
                self.assertEqual(
                    result["status"], "PENDING_OPERATOR_PUBLICATION"
                )

    def test_suffix_only_direct_readback_is_not_canonical(self):
        lookalike = self.ISSUE_URL.replace(
            "api.github.com", "api.github.test"
        ).replace("weijunswj/", "example/").replace(
            "ai-executor-evaluation-ledger/", "ledger/"
        )
        result = self.publish(
            lookalike,
            lambda body: [
                {
                    "id": 81,
                    "issue_url": lookalike,
                    "body": body,
                }
            ],
        )
        self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")


if __name__ == "__main__":
    unittest.main()
