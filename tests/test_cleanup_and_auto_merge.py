import unittest
from unittest.mock import patch, MagicMock
from scripts.processor.cleanup_classifier import classify_pr_scope
from scripts.processor.cleanup_workflow import run_cleanup

class TestCleanupAndAutoMerge(unittest.TestCase):
    def test_standalone_cleanup_only_classifier(self):
        changed_files = [
            "ledger/receipts/cleanup/batch-20260729-gate3-002.json"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "CLEANUP_ONLY")
        self.assertTrue(res["auto_merge_allowed"])

    def test_generated_file_change_requires_semantic_review(self):
        changed_files = [
            "ledger/receipts/cleanup/batch-20260729-gate3-002.json",
            "README.md",
            "scorecard.md"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "SEMANTIC_EVALUATION")
        self.assertFalse(res["auto_merge_allowed"])

    def test_evaluations_jsonl_requires_semantic_review(self):
        changed_files = [
            "evaluations.jsonl"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "SEMANTIC_EVALUATION")
        self.assertFalse(res["auto_merge_allowed"])

    def test_workflow_change_requires_semantic_review(self):
        changed_files = [
            ".github/workflows/post-merge-cleanup.yml"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "SEMANTIC_EVALUATION")
        self.assertFalse(res["auto_merge_allowed"])

    @patch("scripts.processor.cleanup_workflow.fetch_live_comment")
    def test_dry_run_performs_no_writes(self, mock_fetch):
        mock_fetch.return_value = {"id": 1001, "body": "test"}
        result = run_cleanup(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertIn("status", result)
        self.assertNotEqual(result.get("exact_result"), "SUCCESS")

    @patch("scripts.processor.cleanup_workflow.fetch_live_comment")
    def test_disabled_activation_performs_no_delete(self, mock_fetch):
        mock_fetch.return_value = {"id": 1001, "body": "test"}
        result = run_cleanup(dry_run=True)
        self.assertEqual(result["status"], "DRY_RUN_PASSED")
        for rec in result.get("cleanup_receipts", []):
            self.assertEqual(rec.get("exact_result"), "DRY_RUN_PASSED")

    def test_cleanup_only_pr_contains_exactly_one_authorised_receipt_path(self):
        valid = ["ledger/receipts/cleanup/batch-20260729-gate3-amendment-003.json"]
        res = classify_pr_scope(valid)
        self.assertEqual(res["scope"], "CLEANUP_ONLY")
        self.assertTrue(res["auto_merge_allowed"])

        invalid = ["ledger/receipts/cleanup/batch-20260729-gate3-amendment-003.json", "evaluations.jsonl"]
        res_inv = classify_pr_scope(invalid)
        self.assertEqual(res_inv["scope"], "SEMANTIC_EVALUATION")
        self.assertFalse(res_inv["auto_merge_allowed"])

if __name__ == "__main__":
    unittest.main()
