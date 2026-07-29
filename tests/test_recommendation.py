import unittest
import json
import os
from pathlib import Path
from scripts.rebuild_views import generate_recommendation_manifest, render_recommendation_section, resolved_evaluations, load_records

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
        manifest = generate_recommendation_manifest(self.sample_evals)
        self.assertEqual(manifest["official_recorded_gated_evaluations"], 2)
        self.assertEqual(manifest["total_queued_evaluations"], 0)
        self.assertEqual(manifest["total_available_evaluations"], 2)

    def test_gated_v1_ranking_precedence(self):
        # Even though run-unknown-01 has score 4.9, it's protocol_unknown, so it should not enter official gated ranking
        manifest = generate_recommendation_manifest(self.sample_evals)
        stats = manifest["model_statistics"]
        self.assertIn("Gemini 3.6 Flash", stats)
        self.assertIn("DeepSeek V4 Pro", stats)
        self.assertNotIn("GPT-5.6 Sol", stats)

    def test_shuffled_input_determinism(self):
        import copy, random
        evals_shuffled = copy.deepcopy(self.sample_evals)
        random.seed(42)
        random.shuffle(evals_shuffled)
        manifest1 = generate_recommendation_manifest(self.sample_evals)
        manifest2 = generate_recommendation_manifest(evals_shuffled)
        self.assertEqual(manifest1["official_recorded_gated_evaluations"], manifest2["official_recorded_gated_evaluations"])
        self.assertEqual(manifest1["model_statistics"].keys(), manifest2["model_statistics"].keys())

    def test_rendered_recommendation_text(self):
        manifest = generate_recommendation_manifest(self.sample_evals)
        text = render_recommendation_section(manifest)
        self.assertIn("AI Model Recommendations & Operational Guidance", text)
        self.assertIn("Gemini 3.6 Flash", text)
        self.assertIn("DeepSeek V4 Pro", text)

if __name__ == "__main__":
    unittest.main()
