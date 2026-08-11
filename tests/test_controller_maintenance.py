from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import rebuild_views
from scripts.check_public_safety import scan_public_text
from scripts.validate_receipts import (
    LEGACY_FROZEN_RECEIPT_AUTHORITY,
    _running_on_canonical_main,
)

ROOT = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


class TestControllerLedgerMaintenance(unittest.TestCase):
    def test_controller_evaluation_scope_is_exact_four_files(self):
        required = {
            "README.md",
            "analysis/model-recommendation.json",
            "evaluations.jsonl",
            "scorecard.md",
        }
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/evaluation-*', workflow)
                self.assertIn('git diff --name-only "$BASE_SHA" "$HEAD_SHA"', workflow)
                self.assertIn("legacy_context=true", workflow)
                for path in required:
                    self.assertIn(path, workflow)

    def test_controller_maintenance_scope_is_exact_three_files(self):
        required = {
            ".github/workflows/ci.yml",
            ".github/workflows/public-safety.yml",
            "tests/test_controller_maintenance.py",
        }
        forbidden = {"scripts/validate_receipts.py"}
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/ledger-maintenance-*', workflow)
                self.assertIn('git diff --name-only "$BASE_SHA" "$HEAD_SHA"', workflow)
                self.assertIn("legacy_context=true", workflow)
                for path in required:
                    self.assertIn(path, workflow)
                for path in forbidden:
                    self.assertNotIn(f"{path} | sort)", workflow)

    def test_ci_contains_durable_controller_evaluation_transport(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("append-controller-evaluation:", workflow)
        self.assertIn("startsWith(github.ref_name, 'controller/evaluation-')", workflow)
        self.assertIn("startsWith(github.head_ref, 'controller/evaluation-')", workflow)
        self.assertIn("github.event.action == 'opened'", workflow)
        self.assertIn("github.actor != 'github-actions[bot]'", workflow)
        self.assertIn("github.event.pull_request.head.sha || github.sha", workflow)
        self.assertIn("github.head_ref || github.ref_name", workflow)
        self.assertIn(".controller-evaluation-intake.json", workflow)
        self.assertIn("controller intake weighted score mismatch", workflow)
        self.assertIn("controller evaluation already recorded", workflow)
        self.assertIn("python scripts/rebuild_views.py --check --base-ref", workflow)
        self.assertIn("python scripts/validate_manifests.py --base-ref", workflow)
        self.assertIn("python scripts/check_public_safety.py", workflow)
        self.assertIn("git push origin HEAD:${TARGET_BRANCH}", workflow)

    def test_transport_requires_exact_one_file_intake_and_exact_four_file_result(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn('git rev-list --count "$base"..HEAD', workflow)
        self.assertIn('git diff --name-only "$base" HEAD', workflow)
        self.assertIn('= ".controller-evaluation-intake.json"', workflow)
        for path in (
            "README.md",
            "analysis/model-recommendation.json",
            "evaluations.jsonl",
            "scorecard.md",
        ):
            self.assertIn(path, workflow)
        self.assertIn("intake_path.unlink()", workflow)

    def test_data_only_evaluation_delta_has_context_specific_test_gate(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("data_only_evaluation=false", workflow)
                self.assertIn('"$HEAD_REF" == controller/evaluation-*', workflow)
                self.assertIn('"$EVENT_NAME" == "push" && "$REF_NAME" == "main"', workflow)
                self.assertIn("python -m unittest tests.test_controller_maintenance", workflow)
                expected = "printf '%s\\n' README.md analysis/model-recommendation.json evaluations.jsonl scorecard.md | sort"
                self.assertIn(expected, workflow)

    def test_transport_commits_before_final_receipt_validation_and_push(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        commit_index = workflow.index("git commit -m 'Append controller evaluation'")
        receipt_index = workflow.rindex("python scripts/validate_receipts.py --mode pr --authority-sha HEAD")
        clean_index = workflow.index('test -z "$(git status --porcelain)"')
        push_index = workflow.index("git push origin HEAD:${TARGET_BRANCH}")
        self.assertLess(commit_index, receipt_index)
        self.assertLess(receipt_index, clean_index)
        self.assertLess(clean_index, push_index)

    def test_main_push_requires_frozen_receipt_bytes_unchanged(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(
                'git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- ledger/receipts/batches',
                workflow,
            )

    def test_maintenance_lane_still_runs_complete_suite(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("GITHUB_EVENT_NAME=push GITHUB_REF_NAME=main python -m unittest discover", workflow)
            self.assertIn("controller/ledger-maintenance-*", workflow)

    def test_luna_controller_evaluation_reaches_generated_views(self):
        records = rebuild_views.load_records()
        source = next(
            copy.deepcopy(record)
            for record in reversed(records)
            if record.get("record_type") == "evaluation"
        )
        source["run_id"] = "controller-luna-view-generation-probe"
        source["provider"] = "OpenAI"
        source["model"] = "GPT-5.6 Luna"
        source["reviewed_at"] = "2026-08-11T00:00:00Z"
        source["subject_alias"] = "controller-luna-schema-probe"
        source["revision_binding"] = "non-identifying-controller-luna-schema-probe"

        evaluations = rebuild_views.resolved_evaluations([*records, source])
        readme, scorecard, recommendation = rebuild_views.expected_files(evaluations)

        self.assertIn("GPT-5.6 Luna", readme)
        self.assertIn("GPT-5.6 Luna", scorecard)
        self.assertIn("GPT-5.6 Luna", json.dumps(recommendation, sort_keys=True))

    def test_luna_execution_setting_identity_is_rejected_by_public_safety(self):
        failures = scan_public_text("probe", "GPT-5.6 Luna Max")
        self.assertTrue(failures, "Luna execution-setting identity must fail closed")

    def test_main_context_never_leaks_into_fixture_repositories(self):
        actual_head = git(ROOT, "rev-parse", "HEAD")
        with mock.patch.dict(
            os.environ,
            {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"},
            clear=True,
        ):
            self.assertTrue(_running_on_canonical_main(ROOT, actual_head))

        with tempfile.TemporaryDirectory(prefix="ledger-main-context-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            (root / "file.txt").write_text("one\n", encoding="utf-8")
            git(root, "add", "file.txt")
            git(root, "commit", "-qm", "one")
            head = git(root, "rev-parse", "HEAD")

            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertFalse(_running_on_canonical_main(root, head))
            with mock.patch.dict(
                os.environ,
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"},
                clear=True,
            ):
                self.assertFalse(_running_on_canonical_main(root, head))

    def test_legacy_receipt_authority_is_exact_public_pr151_terminal(self):
        self.assertEqual(
            "2d4ec54c4a922ee37d0ae53a52a9c97732fb76d8",
            LEGACY_FROZEN_RECEIPT_AUTHORITY,
        )

    def test_normal_pull_request_receipt_mode_remains_strict(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("--mode pr", workflow)
            self.assertIn('--authority-sha "$HEAD_SHA"', workflow)
            self.assertNotIn("continue-on-error", workflow)


if __name__ == "__main__":
    unittest.main()
