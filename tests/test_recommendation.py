import unittest
import json
import copy, random
from scripts.rebuild_views import generate_recommendation_manifest, render_recommendation_section, rebuild_views

class TestRecommendationAndViews(unittest.TestCase):
    def setUp(self):
        self.sample_evals = [
            {
                "run_id": "run-gated-01",
                "record_type": "evaluation",
                "reviewed_at": "2026-07-28T10:00:00Z",
                "provider": "Google",
                "model": "Gemini 3.6 Flash",
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
        rebuild_views()
        manifest1 = json.dumps(generate_recommendation_manifest(self.sample_evals), indent=2)
        manifest2 = json.dumps(generate_recommendation_manifest(self.sample_evals), indent=2)
        self.assertEqual(manifest1, manifest2)

if __name__ == "__main__":
    unittest.main()
