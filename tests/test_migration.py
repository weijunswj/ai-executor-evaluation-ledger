import unittest
import json
import hashlib
import os

class TestMigrationAndPreservation(unittest.TestCase):
    def setUp(self):
        self.jsonl_path = "evaluations.jsonl"
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            self.records = [json.loads(line) for line in f if line.strip()]

    def test_record_counts(self):
        evals = [r for r in self.records if r.get("record_type") == "evaluation"]
        corrs = [r for r in self.records if r.get("record_type") == "correction"]
        self.assertGreaterEqual(len(evals), 58)
        self.assertGreaterEqual(len(corrs), 1)

    def test_withdrawn_records_absent(self):
        withdrawn_ids = {
            "2026-07-24-claude-opus-4-8-business-automation-a-implementation-001",
            "2026-07-24-claude-opus-4-8-business-automation-a-amendment-001",
            "2026-07-24-claude-opus-4-8-high-business-automation-a-amendment-002",
            "2026-07-24-claude-opus-4-8-ultra-high-business-automation-a-amendment-003",
            "2026-07-24-correction-claude-opus-4-8-high-implementation-001",
            "2026-07-24-correction-claude-opus-4-8-high-amendment-001"
        }
        present_ids = {r.get("run_id") for r in self.records}
        self.assertTrue(withdrawn_ids.isdisjoint(present_ids))

    def test_reasoning_only_correction_removed(self):
        present_ids = {r.get("run_id") for r in self.records}
        self.assertNotIn("2026-07-25-correction-mimo-2-5-pro-default-provenance-repair-003", present_ids)
        self.assertIn("2026-07-26-correction-gpt-5-6-sol-workflow-compatibility-gate1-reset-001", present_ids)

    def test_no_reasoning_metadata(self):
        forbidden_keys = {
            "requested_" + "reasoning" + "_level",
            "observed_" + "reasoning" + "_mode",
            "thinking_" + "setting",
            "native_" + "reasoning" + "_classification",
            "reasoning" + "_exposure_status",
            "reasoning" + "_grouping",
        }
        for r in self.records:
            keys = set(r.keys())
            self.assertTrue(forbidden_keys.isdisjoint(keys), f"Record {r.get('run_id')} contains forbidden keys: {keys.intersection(forbidden_keys)}")
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
