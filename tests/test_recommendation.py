import unittest
import json
import copy, random
from pathlib import Path
from scripts.rebuild_views import expected_files_for_records, generate_recommendation_manifest

ROOT = Path(__file__).resolve().parents[1]

class TestRecommendationAndViews(unittest.TestCase):
    def setUp(self):
        self.sample_evals = [
            {
                "run_id": "run-gated-01",
                "record_type": "evaluation",
                "reviewed_at": "2026-07-28T10:00:00Z",
                "provider": "Google",
                "model": "Gemini 3.1 Pro",
                "evaluation_protocol": "gated_v1",
                "task_class": "research",
                "difficulty": "medium",
                "subject_alias": "sub-a",
                "outcome": "accepted",
                "weighted_score_5": 4.8,
                "first_pass_accepted": True,
                "safe_final_state_verified": True
            },
            {
                "run_id": "run-gated-02",
                "record_type": "evaluation",
                "reviewed_at": "2026-07-28T11:00:00Z",
                "provider": "DeepSeek",
                "model": "DeepSeek V4 Pro",
                "evaluation_protocol": "gated_v1",
                "task_class": "research",
                "difficulty": "medium",
                "subject_alias": "sub-b",
                "outcome": "accepted",
                "weighted_score_5": 4.5,
                "first_pass_accepted": True,
                "safe_final_state_verified": True
            },
            {
                "run_id": "run-unknown-01",
                "record_type": "evaluation",
                "reviewed_at": "2026-07-27T10:00:00Z",
                "provider": "OpenAI",
                "model": "GPT-5.6 Sol",
                "evaluation_protocol": "protocol_unknown",
                "task_class": "research",
                "difficulty": "high",
                "subject_alias": "sub-c",
                "outcome": "accepted",
                "weighted_score_5": 4.9,
                "first_pass_accepted": True,
                "safe_final_state_verified": True
            }
        ]

    def test_recommendation_manifest_counts(self):
        manifest = generate_recommendation_manifest(self.sample_evals, total_queued_count=10)
        self.assertEqual(manifest["official_recorded_gated_evaluations"], 2)
        self.assertEqual(manifest["total_queued_evaluations"], 10)
        self.assertEqual(manifest["total_available_evaluations"], 12)

    def test_shuffled_input_determinism(self):
        evals_shuffled = copy.deepcopy(self.sample_evals)
        random.seed(42)
        random.shuffle(evals_shuffled)
        manifest1 = generate_recommendation_manifest(self.sample_evals, total_queued_count=5)
        manifest2 = generate_recommendation_manifest(evals_shuffled, total_queued_count=5)
        self.assertEqual(manifest1, manifest2)

    def test_byte_identical_rebuild_twice(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        scorecard = (ROOT / "scorecard.md").read_text(encoding="utf-8")
        first = expected_files_for_records(self.sample_evals, readme, scorecard)
        second = expected_files_for_records(self.sample_evals, readme, scorecard)
        self.assertEqual(first, second)

    def test_recorded_queued_available_counts_math(self):
        recorded = 5
        queued_pending = 3
        sample = self.sample_evals[:2] # 2 gated_v1
        manifest = generate_recommendation_manifest(sample, total_queued_count=queued_pending)
        self.assertEqual(manifest["official_recorded_gated_evaluations"], 2)
        self.assertEqual(manifest["total_queued_evaluations"], 3)
        self.assertEqual(manifest["total_available_evaluations"], 5)

    def test_comment_count_is_not_queued_evaluation_count(self):
        total_raw_comments_in_queue = 98
        valid_pending_evaluations = 18
        manifest = generate_recommendation_manifest(self.sample_evals, total_queued_count=valid_pending_evaluations)
        self.assertNotEqual(manifest["total_queued_evaluations"], total_raw_comments_in_queue)
        self.assertEqual(manifest["total_queued_evaluations"], valid_pending_evaluations)

if __name__ == "__main__":
    unittest.main()
