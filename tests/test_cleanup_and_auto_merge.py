import unittest
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

    def test_dry_run_performs_no_writes(self):
        result = run_cleanup(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertIn("status", result)
        self.assertNotEqual(result.get("exact_result"), "SUCCESS") # Dry run must not report live SUCCESS

if __name__ == "__main__":
    unittest.main()
