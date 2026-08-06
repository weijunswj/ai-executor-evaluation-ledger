import unittest
import json
import hashlib
import os

from scripts.processor.common import REASONING_KEYS
from scripts.validate_manifests import (
    REASONING_ONLY_REMOVED,
    REPLACEMENTS,
    SCORE_VALUES,
    WITHDRAWN_IDS,
)


class TestMigrationAndPreservation(unittest.TestCase):
    def setUp(self):
        self.jsonl_path = "evaluations.jsonl"
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            self.records = [json.loads(line) for line in f if line.strip()]

    def test_record_counts(self):
        evals = [r for r in self.records if r.get("record_type") == "evaluation"]
        corrs = [r for r in self.records if r.get("record_type") == "correction"]
        self.assertEqual(len(evals), 58)
        self.assertEqual(len(corrs), 1)
        self.assertEqual(len(self.records), 59)

    def test_g3_locked_record_sets_and_score_corrections(self):
        with open("migrations/correction-records-v3.jsonl", "r", encoding="utf-8") as f:
            corrections = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(self.records), 59)
        self.assertEqual(len(corrections), 116)
        self.assertEqual(
            set(REPLACEMENTS.values()),
            {
                record["replacement"]["replacement_run_id"]
                for record in corrections
                if record["record_type"] == "base_model_replacement"
            },
        )
        self.assertTrue(set(WITHDRAWN_IDS).isdisjoint({record["run_id"] for record in self.records}))
        observed_scores = {
            record["target"]["run_id"]: tuple(
                str(change["after_public_safe"])
                for change in record["correction"]["field_changes"]
            )
            for record in corrections
            if record["record_type"] == "factual_correction"
        }
        self.assertEqual(observed_scores, SCORE_VALUES)

    def test_withdrawn_records_absent(self):
        present_ids = {r.get("run_id") for r in self.records}
        self.assertTrue(set(WITHDRAWN_IDS).isdisjoint(present_ids))

    def test_reasoning_only_correction_removed(self):
        present_ids = {r.get("run_id") for r in self.records}
        self.assertNotIn(REASONING_ONLY_REMOVED, present_ids)

    def test_no_reasoning_metadata(self):
        forbidden_keys = set(REASONING_KEYS)
        for r in self.records:
            keys = set(r.keys())
            self.assertTrue(forbidden_keys.isdisjoint(keys))
            if r.get("record_type") == "correction":
                cfields = set(r.get("corrected_fields", {}).keys())
                self.assertTrue(forbidden_keys.isdisjoint(cfields))

    def test_schema_v2_and_protocol(self):
        allowed_protocols = {"gated_v1", "legacy_pre_gate", "protocol_unknown"}
        for r in self.records:
            self.assertEqual(r.get("schema_version"), 2)
            self.assertIn(r.get("evaluation_protocol"), allowed_protocols)

    def test_explicit_model_map(self):
        allowed_models = {
            "MiMo 2.5 Pro",
            "Claude Opus 4.8",
            "Claude Opus 5",
            "DeepSeek V4 Pro",
            "GPT-5.6 Sol",
            "Qwen3.7 Plus",
            "Gemini 3.1 Pro",
            "Gemini 3.6 Flash",
            "MiniMax M3"
        }
        for r in self.records:
            model = r.get("model")
            self.assertIn(model, allowed_models, f"Model '{model}' not in allowed canonical models")

    def test_manifests_exist(self):
        self.assertTrue(os.path.exists("migrations/base-model-v2.json"))
        self.assertTrue(os.path.exists("migrations/evaluation-protocol-v1.json"))
        self.assertTrue(os.path.exists("migrations/reasoning-scrub-receipt.json"))
        self.assertTrue(os.path.exists("migrations/correction-migration-manifest.json"))

if __name__ == "__main__":
    unittest.main()
