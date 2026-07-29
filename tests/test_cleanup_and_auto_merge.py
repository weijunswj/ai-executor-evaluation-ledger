import unittest
from scripts.processor.cleanup_classifier import classify_pr_scope
from scripts.processor.cleanup_workflow import run_cleanup

class TestCleanupAndAutoMerge(unittest.TestCase):
    def test_cleanup_only_classifier(self):
        changed_files = [
            "ledger/receipts/cleanup/batch-001.json",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "CLEANUP_ONLY")
        self.assertTrue(res["auto_merge_allowed"])

    def test_semantic_evaluation_classifier(self):
        changed_files = [
            "evaluations.jsonl",
            "README.md"
        ]
        res = classify_pr_scope(changed_files)
        self.assertEqual(res["scope"], "SEMANTIC_EVALUATION")
        self.assertFalse(res["auto_merge_allowed"])

    def test_workflow_change_prevents_auto_merge(self):
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

if __name__ == "__main__":
    unittest.main()
