import copy
import json
import random
import unittest
from pathlib import Path

import jsonschema

from scripts.rebuild_views import (
    INDEPENDENT_OBSERVATION_THRESHOLD,
    expected_files_for_records,
    generate_recommendation_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def evaluation(
    run_id,
    model,
    subject,
    *,
    task="research",
    difficulty="medium",
    score=4.0,
    first_pass=True,
    intervention=False,
    queued_source=None,
    defect="shared defect",
    revision="a" * 40,
    stage="implementation",
    environment="repository-cli",
    operation="gate3",
):
    providers = {
        "Gemini 3.1 Pro": "Google",
        "DeepSeek V4 Pro": "DeepSeek",
        "GPT-5.6 Sol": "OpenAI",
    }
    value = {
        "run_id": run_id,
        "record_type": "evaluation",
        "reviewed_at": "2026-07-28T10:00:00Z",
        "provider": providers[model],
        "model": model,
        "evaluation_protocol": "gated_v1",
        "task_class": task,
        "difficulty": difficulty,
        "subject_alias": subject,
        "revision_binding": revision,
        "task_stage": stage,
        "tool_environment_class": environment,
        "operation_gate_type": operation,
        "outcome": "accepted" if first_pass else "amend",
        "weighted_score_5": score,
        "first_pass_accepted": first_pass,
        "controller_intervention_required": intervention,
        "safe_final_state_verified": True,
        "scores": {
            "safety_and_scope_control": score,
            "evidence_quality": max(0, score - 0.5),
            "efficiency": max(0, score - 1),
        },
        "verified_defects": [defect],
    }
    if queued_source is not None:
        value["source_comment_id"] = queued_source
    return value


class TestRecommendationAndViews(unittest.TestCase):
    def setUp(self):
        self.sample_evals = [
            evaluation("gemini-1", "Gemini 3.1 Pro", "subject-a", score=4.8),
            evaluation("deepseek-1", "DeepSeek V4 Pro", "subject-a", score=4.5),
            evaluation("gemini-2", "Gemini 3.1 Pro", "subject-b", score=4.7),
            evaluation("deepseek-2", "DeepSeek V4 Pro", "subject-b", score=4.4),
            evaluation("gemini-3", "Gemini 3.1 Pro", "subject-c", score=4.6),
            evaluation("deepseek-3", "DeepSeek V4 Pro", "subject-c", score=4.3),
        ]

    def test_explicit_recorded_queued_available_populations(self):
        queued = [
            evaluation(
                "queued-sol-1",
                "GPT-5.6 Sol",
                "subject-q",
                queued_source=901,
            )
        ]
        manifest = generate_recommendation_manifest(self.sample_evals, queued)
        self.assertEqual(manifest["populations"]["recorded"]["count"], 6)
        self.assertEqual(manifest["populations"]["queued"]["count"], 1)
        self.assertEqual(manifest["populations"]["available"]["count"], 7)
        self.assertEqual(manifest["model_statistics"]["GPT-5.6 Sol"]["queued_count"], 1)
        self.assertEqual(manifest["model_statistics"]["GPT-5.6 Sol"]["recorded_count"], 0)

    def test_scalar_queue_count_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_recommendation_manifest(self.sample_evals, 10)

    def test_queue_identity_and_source_binding_must_be_unique(self):
        queued = [
            evaluation("queued-1", "GPT-5.6 Sol", "subject-q1", queued_source=901),
            evaluation("queued-2", "GPT-5.6 Sol", "subject-q2", queued_source=901),
        ]
        with self.assertRaises(ValueError):
            generate_recommendation_manifest(self.sample_evals, queued)
        conflicting = [
            evaluation("gemini-1", "GPT-5.6 Sol", "subject-q1", queued_source=902)
        ]
        with self.assertRaises(ValueError):
            generate_recommendation_manifest(self.sample_evals, conflicting)

    def test_exact_and_similar_cohorts_are_separately_counted(self):
        similar_only = [
            evaluation("sol-similar", "GPT-5.6 Sol", "different-subject", score=4.2)
        ]
        manifest = generate_recommendation_manifest(self.sample_evals + similar_only, [])
        sol = manifest["model_statistics"]["GPT-5.6 Sol"]
        self.assertEqual(sol["exact_matched_cohort_count"], 0)
        self.assertEqual(sol["similar_matched_cohort_count"], 1)
        self.assertEqual(sol["raw_comparable_run_count"], 1)

    def test_correlated_amendment_chain_counts_as_one_subject(self):
        correlated = [
            evaluation("gemini-amend-1", "Gemini 3.1 Pro", "subject-a", score=4.1),
            evaluation("gemini-amend-2", "Gemini 3.1 Pro", "subject-a", score=4.2),
        ]
        manifest = generate_recommendation_manifest(self.sample_evals + correlated, [])
        stats = manifest["model_statistics"]["Gemini 3.1 Pro"]
        self.assertEqual(stats["recorded_count"], 5)
        self.assertEqual(stats["independent_subject_count"], 3)
        self.assertTrue(
            any("correlated subject chain" in item for item in stats["material_limitations"])
        )

    def test_strongest_model_uses_exact_matches_not_overall_average(self):
        unmatched_high = [
            evaluation(
                "deepseek-unmatched",
                "DeepSeek V4 Pro",
                "unmatched-subject",
                task="coding",
                score=5.0,
            )
        ]
        manifest = generate_recommendation_manifest(self.sample_evals + unmatched_high, [])
        self.assertEqual(
            manifest["recommendation"]["status"],
            "strongest_on_exact_matched_evidence",
        )
        self.assertEqual(manifest["recommendation"]["model"], "Gemini 3.1 Pro")

    def test_weak_overlap_or_different_task_mix_declares_no_strongest(self):
        weak = self.sample_evals[:4]
        weak_manifest = generate_recommendation_manifest(weak, [])
        self.assertEqual(
            weak_manifest["recommendation"]["status"],
            "insufficient_comparable_evidence",
        )
        self.assertIsNone(weak_manifest["recommendation"]["model"])

        different_mix = list(self.sample_evals)
        for index in range(3):
            subject = f"subject-docs-{index}"
            different_mix.extend(
                [
                    evaluation(
                        f"gemini-docs-{index}",
                        "Gemini 3.1 Pro",
                        subject,
                        task="documentation",
                    ),
                    evaluation(
                        f"sol-docs-{index}",
                        "GPT-5.6 Sol",
                        subject,
                        task="documentation",
                    ),
                ]
            )
        different_manifest = generate_recommendation_manifest(different_mix, [])
        self.assertEqual(
            different_manifest["recommendation"]["status"],
            "insufficient_comparable_evidence",
        )

    def test_required_model_evidence_and_undersampling_gaps(self):
        queued = [
            evaluation(
                "queued-sol-1",
                "GPT-5.6 Sol",
                "subject-q",
                difficulty="high",
                queued_source=901,
            )
        ]
        manifest = generate_recommendation_manifest(self.sample_evals, queued)
        stats = manifest["model_statistics"]["Gemini 3.1 Pro"]
        for field in (
            "recorded_count",
            "queued_count",
            "available_count",
            "raw_comparable_run_count",
            "independent_subject_count",
            "exact_matched_cohort_count",
            "similar_matched_cohort_count",
            "verdict_distribution",
            "first_pass_acceptance",
            "controller_intervention",
            "score_evidence",
            "recurring_defect_patterns",
            "material_limitations",
            "undersampling",
        ):
            self.assertIn(field, stats)
        sol_gap = manifest["model_statistics"]["GPT-5.6 Sol"]["undersampling"]
        self.assertTrue(sol_gap["under_sampled"])
        self.assertEqual(
            sol_gap["additional_independent_observations_required"],
            INDEPENDENT_OBSERVATION_THRESHOLD,
        )
        self.assertTrue(sol_gap["missing_cross_model_matched_cohort"])
        self.assertEqual(sol_gap["missing_difficulties"], ["medium"])

    def test_exact_cohorts_require_revision_stage_environment_and_operation(self):
        variants = [
            evaluation(
                "same-subject-different-revision",
                "GPT-5.6 Sol",
                "subject-a",
                revision="b" * 40,
            ),
            evaluation(
                "same-revision-different-stage",
                "GPT-5.6 Sol",
                "subject-a",
                stage="amendment",
            ),
            evaluation(
                "different-environment",
                "GPT-5.6 Sol",
                "subject-a",
                environment="hosted-review",
            ),
            evaluation(
                "different-operation",
                "GPT-5.6 Sol",
                "subject-a",
                operation="gate4",
            ),
        ]
        manifest = generate_recommendation_manifest(self.sample_evals + variants, [])
        sol = manifest["model_statistics"]["GPT-5.6 Sol"]
        self.assertEqual(sol["exact_matched_cohort_count"], 0)
        self.assertEqual(sol["exact_cohort_eligible_recorded_count"], 4)

    def test_implementation_amendment_and_gate4_are_not_exact(self):
        lineage = [
            evaluation(
                "implementation",
                "Gemini 3.1 Pro",
                "lineage",
                stage="implementation",
                operation="gate3",
            ),
            evaluation(
                "amendment",
                "DeepSeek V4 Pro",
                "lineage",
                stage="amendment",
                operation="gate3",
            ),
            evaluation(
                "gate4-review",
                "GPT-5.6 Sol",
                "lineage",
                stage="review",
                operation="gate4",
            ),
        ]
        manifest = generate_recommendation_manifest(lineage, [])
        for stats in manifest["model_statistics"].values():
            self.assertEqual(stats["exact_matched_cohort_count"], 0)

    def test_queued_only_coverage_never_grants_official_eligibility(self):
        queued = [
            evaluation(
                f"queued-sol-{index}",
                "GPT-5.6 Sol",
                f"queued-subject-{index}",
                queued_source=900 + index,
            )
            for index in range(1, INDEPENDENT_OBSERVATION_THRESHOLD + 1)
        ]
        manifest = generate_recommendation_manifest(self.sample_evals, queued)
        sol = manifest["model_statistics"]["GPT-5.6 Sol"]
        self.assertEqual(sol["independent_subject_count"], 0)
        self.assertNotIn("GPT-5.6 Sol", manifest["recommendation"]["compared_models"])

    def test_unknown_dimensions_are_explicit_and_excluded_from_exact_cohorts(self):
        unknown = evaluation("unknown-stage", "GPT-5.6 Sol", "subject-a")
        del unknown["task_stage"]
        manifest = generate_recommendation_manifest(self.sample_evals + [unknown], [])
        identity = manifest["cohort_identities"]["unknown-stage"]
        self.assertEqual(identity["task_stage"], "unknown")
        sol = manifest["model_statistics"]["GPT-5.6 Sol"]
        self.assertEqual(sol["exact_cohort_eligible_recorded_count"], 0)
        self.assertEqual(sol["exact_cohort_unknown_recorded_count"], 1)
        self.assertEqual(sol["exact_matched_cohort_count"], 0)

    def test_correlated_chain_uses_subject_revision_and_task_lineage(self):
        correlated = [
            evaluation("chain-a", "Gemini 3.1 Pro", "subject-chain", score=4.1),
            evaluation(
                "chain-b",
                "Gemini 3.1 Pro",
                "subject-chain",
                stage="amendment",
                score=4.2,
            ),
        ]
        different_revision = evaluation(
            "chain-c",
            "Gemini 3.1 Pro",
            "subject-chain",
            revision="c" * 40,
            score=4.3,
        )
        manifest = generate_recommendation_manifest(
            correlated + [different_revision],
            [],
        )
        self.assertEqual(
            manifest["model_statistics"]["Gemini 3.1 Pro"]["independent_subject_count"],
            2,
        )

    def test_rebuild_workflow_tracks_and_commits_recommendation(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rebuild-ledger-views.yml"
        ).read_text(encoding="utf-8")
        artifact = "analysis/model-recommendation.json"
        self.assertGreaterEqual(workflow.count(artifact), 3)
        self.assertIn(
            f"git diff --quiet -- README.md scorecard.md {artifact}",
            workflow,
        )
        self.assertIn(f"git add README.md scorecard.md {artifact}", workflow)

    def test_manifest_is_closed_schema_and_shuffle_stable(self):
        queued = [
            evaluation("queued-sol-1", "GPT-5.6 Sol", "subject-q1", queued_source=901),
            evaluation("queued-sol-2", "GPT-5.6 Sol", "subject-q2", queued_source=902),
        ]
        recorded_shuffled = copy.deepcopy(self.sample_evals)
        queued_shuffled = copy.deepcopy(queued)
        random.Random(42).shuffle(recorded_shuffled)
        random.Random(73).shuffle(queued_shuffled)
        first = generate_recommendation_manifest(self.sample_evals, queued)
        second = generate_recommendation_manifest(recorded_shuffled, queued_shuffled)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, indent=2),
            json.dumps(second, sort_keys=True, indent=2),
        )
        schema = json.loads(
            (ROOT / "schema" / "recommendation.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(first)
        leaked = copy.deepcopy(first)
        leaked["unexpected"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(leaked)

    def test_byte_identical_view_construction_and_section_order(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        scorecard = (ROOT / "scorecard.md").read_text(encoding="utf-8")
        first = expected_files_for_records(self.sample_evals, readme, scorecard, [])
        second = expected_files_for_records(self.sample_evals, readme, scorecard, [])
        self.assertEqual(first, second)
        self.assertLess(
            first[0].index("## AI Model Recommendations & Operational Guidance"),
            first[0].index("## Summary model scores"),
        )
        self.assertNotIn("Current task-fit summary", first[0])


if __name__ == "__main__":
    unittest.main()
