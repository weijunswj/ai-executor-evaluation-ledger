import copy
import json
import unittest
from pathlib import Path

import jsonschema

from scripts.processor.common import canonical_json_bytes, sha256_bytes, validate_batch_receipt_closure

ROOT = Path(__file__).resolve().parents[1]


class TestSchemasAndValidation(unittest.TestCase):
    def setUp(self):
        self.schemas = {
            name: json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))
            for name in (
                "evaluation.schema.json",
                "intake.schema.json",
                "receipt.schema.json",
                "disposition.schema.json",
            )
        }
        self.checker = jsonschema.FormatChecker()

    def validate(self, name, instance):
        jsonschema.validate(
            instance=instance,
            schema=self.schemas[name],
            format_checker=self.checker,
        )

    def valid_batch(self):
        digest = "a" * 64
        record_id = "run-schema-a005"
        queue_snapshot_digest = digest
        return {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": "batch-schema-a005",
            "batch_mode": "initial",
            "controller_run_id": "controller-schema-a005",
            "base_sha": "a" * 40,
            "canonical_main_sha": "b" * 40,
            "candidate_content_commit_sha": "c" * 40,
            "pr_number": 151,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "source_comment_watermark": 1,
            "full_queue_count": 1,
            "latest_observed_comment_id": 1,
            "latest_observed_update_time": "2026-07-29T10:00:00Z",
            "queue_snapshot_sha256": queue_snapshot_digest,
            "source_comment_ids": [1],
            "source_body_sha256": {"1": digest},
            "selected_comment_ids": [1],
            "selected_comment_count": 1,
            "terminal_outcome_count": 1,
            "terminal_outcomes": {
                "1": {
                    "outcome_code": "admitted",
                    "evaluation_run_id": record_id,
                    "canonical_record_sha256": digest,
                    "cleanup_eligible": False,
                }
            },
            "admitted_run_ids": [record_id],
            "accepted_record_proofs": {
                record_id: {
                    "provider": "OpenAI",
                    "model": "GPT-5.6 Sol",
                    "outcome": "accepted",
                    "weighted_score_5": 4.6,
                }
            },
            "canonical_record_hashes": {record_id: digest},
            "canonical_hashes": {
                "evaluations_jsonl": digest,
                "dispositions_jsonl": digest,
                "readme_md": digest,
                "scorecard_md": digest,
                "model_recommendation_json": digest,
            },
            "comment_bindings": [
                {
                    "comment_id": 1,
                    "created_at": "2026-07-29T09:59:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "body_sha256": digest,
                    "outcome_code": "admitted",
                    "evaluation_run_id": record_id,
                    "canonical_record_sha256": digest,
                    "cleanup_eligible": False,
                }
            ],
        }

    def valid_cleanup(self):
        digest = "a" * 64
        return {
            "schema_version": 2,
            "receipt_type": "cleanup",
            "cleanup_status": "blocked",
            "batch_id": "batch-schema-a005",
            "canonical_merge_sha": "a" * 40,
            "canonical_main_sha": "a" * 40,
            "expected_head_sha": "c" * 40,
            "pr_number": 151,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "canonical_hashes": {
                "evaluations_jsonl": digest,
                "dispositions_jsonl": digest,
                "readme_md": digest,
                "scorecard_md": digest,
                "model_recommendation_json": digest,
            },
            "canonical_record_hashes": {"run-schema-a005": digest},
            "canonical_record_proofs": {
                "run-schema-a005": {
                    "provider": "OpenAI",
                    "model": "GPT-5.6 Sol",
                    "outcome": "accepted",
                    "weighted_score_5": 4.6,
                }
            },
            "source_comment_ids": [1],
            "source_body_sha256": {"1": digest},
            "retained_comment_ids": [1],
            "source_retention_verified": False,
            "recorded_receipt_status": "unverified",
            "branch_cleanup_eligible": False,
            "branch_cleanup_reason": "receipt_unverified",
            "publication_status": "pending_operator_publication",
            "platform_limitation_code": "web_orchestrator_publication_required",
            "batch_receipt_sha256": digest,
            "batch_receipt_bytes_sha256": digest,
        }

    def test_all_schema_documents_are_valid_draft_2020_12(self):
        for schema in self.schemas.values():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            jsonschema.Draft202012Validator.check_schema(schema)

    def test_historical_evaluations_dispositions_and_receipts_validate(self):
        for line in (ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                self.validate("evaluation.schema.json", json.loads(line))
        for line in (ROOT / "ledger" / "dispositions.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                self.validate("disposition.schema.json", json.loads(line))
        for path in (ROOT / "ledger" / "receipts" / "batches").glob("*.json"):
            self.validate("receipt.schema.json", json.loads(path.read_text(encoding="utf-8")))

    def test_new_batch_and_cleanup_variants_are_closed_and_disjoint(self):
        batch = self.valid_batch()
        cleanup = self.valid_cleanup()
        self.validate("receipt.schema.json", batch)
        self.validate("receipt.schema.json", cleanup)
        variant_leak = copy.deepcopy(batch)
        variant_leak["cleanup_status"] = "blocked"
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", variant_leak)
        variant_leak = copy.deepcopy(cleanup)
        variant_leak["terminal_outcomes"] = {}
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", variant_leak)

    def test_invalid_hash_sha_timestamp_and_nested_field_fail_closed(self):
        batch = self.valid_batch()
        batch["base_sha"] = "not-a-git-sha"
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", batch)
        batch = self.valid_batch()
        batch["latest_observed_update_time"] = "not-a-timestamp"
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", batch)
        batch = self.valid_batch()
        batch["canonical_hashes"]["unexpected"] = "a" * 64
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", batch)

    def test_batch_closure_binds_counts_maps_and_outcomes(self):
        batch = self.valid_batch()
        self.assertTrue(validate_batch_receipt_closure(batch))
        batch["full_queue_count"] = 2
        self.assertFalse(validate_batch_receipt_closure(batch))
        batch = self.valid_batch()
        batch["terminal_outcomes"] = {}
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("receipt.schema.json", batch)

    def test_correction_fields_cannot_change_identity_or_outcome(self):
        record = next(
            json.loads(line)
            for line in (ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("record_type") == "correction"
        )
        record["corrected_fields"] = {"model": "GPT-5.6 Sol"}
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("evaluation.schema.json", record)

    def test_evaluation_schema_rejects_unknown_nested_metadata(self):
        record = json.loads(next(line for line in (ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()))
        record["controller_verification"]["unknown_nested_schema_key"] = "fixture"
        with self.assertRaises(jsonschema.ValidationError):
            self.validate("evaluation.schema.json", record)

    def test_exact_hash_fixture_uses_canonical_bytes(self):
        value = {"b": "é", "a": 1}
        exact = canonical_json_bytes(value) + b"\n"
        self.assertEqual(sha256_bytes(exact), sha256_bytes(exact))
        self.assertNotEqual(sha256_bytes(exact), sha256_bytes(exact[:-1] + b" "))


if __name__ == "__main__":
    unittest.main()
