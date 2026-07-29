import unittest
from pathlib import Path

from scripts.processor.cleanup_classifier import classify_pr_scope
from scripts.processor.cleanup_workflow import publish_cleanup_receipt

ROOT = Path(__file__).resolve().parents[1]


class TestCleanupAndActivation(unittest.TestCase):
    def test_standalone_cleanup_only_classifier_requires_exact_json_leaf_paths(self):
        valid = ["ledger/receipts/cleanup/batch-a005.json"]
        result = classify_pr_scope(valid)
        self.assertEqual(result["scope"], "CLEANUP_ONLY")
        self.assertTrue(result["auto_merge_allowed"])
        for invalid in (
            "ledger/receipts/cleanup/nested/batch.json",
            "ledger/receipts/cleanup/../evaluations.jsonl",
            "ledger/receipts/cleanup/batch.txt",
            "ledger/receipts/cleanup\\batch.json",
            "evaluations.jsonl",
        ):
            rejected = classify_pr_scope([invalid])
            self.assertFalse(rejected["auto_merge_allowed"], invalid)
            self.assertEqual(rejected["scope"], "SEMANTIC_EVALUATION")

    def test_mixed_generated_and_receipt_scope_requires_semantic_review(self):
        result = classify_pr_scope([
            "ledger/receipts/cleanup/batch-a005.json",
            "README.md",
        ])
        self.assertFalse(result["auto_merge_allowed"])

    def test_workflow_is_manual_read_only_and_has_no_source_mutation_command(self):
        workflow = (ROOT / ".github" / "workflows" / "post-merge-cleanup.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("issues: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("issues: write", workflow)
        source = (ROOT / "scripts" / "processor" / "cleanup_workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("-X", source)
        self.assertNotIn("LEDGER_CLEANUP_ENABLED", source)
        self.assertNotIn("delete_live_comment", source)

    def test_publication_requires_reviewed_live_activation(self):
        receipt = {"cleanup_status": "verified", "recorded_receipt_status": "absent"}
        with self.assertRaises(Exception):
            publish_cleanup_receipt(
                receipt,
                activation_mode="dry-run",
                operator_intent="unreviewed",
            )
        result = publish_cleanup_receipt(
            receipt,
            activation_mode="reviewed-live",
            operator_intent="reviewed",
        )
        self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")


if __name__ == "__main__":
    unittest.main()
