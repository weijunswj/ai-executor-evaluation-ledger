from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_public_safety as public_safety
from scripts import rebuild_views
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


def luna_rule_set_sha256(rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    structures = []
    for rule_id, sequence in rules:
        sequence_bytes = (
            json.dumps(sequence, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        structures.append(
            {
                "case_folding": "unicode_casefold",
                "normalized_sequence_sha256": hashlib.sha256(
                    sequence_bytes
                ).hexdigest(),
                "normalization": "NFKC",
                "rule_id": rule_id,
                "token_count": len(sequence),
                "tokenization": "unicode_alphanumeric_runs_v1",
            }
        )
    canonical = (
        json.dumps(
            structures,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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

    def test_luna_execution_setting_identities_are_rejected_by_public_safety(self):
        model_words = ("GPT", "5", "6", "Luna")
        for execution_setting in ("Medium", "High", "Max"):
            ordinary = (
                "-".join(model_words[:2])
                + "."
                + model_words[2]
                + " "
                + model_words[3]
                + " "
                + execution_setting
            )
            fullwidth = "".join(
                chr(ord(character) + 0xFEE0)
                if "!" <= character <= "~"
                else character
                for character in ordinary
            )
            em_dash = chr(0x2014).join((*model_words, execution_setting))
            for identity in (ordinary, fullwidth, em_dash):
                with self.subTest(setting=execution_setting, identity=repr(identity)):
                    failures = public_safety.scan_public_text("probe", identity)
                    self.assertTrue(
                        failures,
                        "Luna execution-setting identity must fail closed",
                    )

    def test_luna_rule_manifest_seals_all_prospective_rules(self):
        manifest_path = ROOT / "migrations" / "luna-execution-setting-history-activation.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest),
            {"schema_version", "manifest_type", "rule_count", "rule_set_sha256"},
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["manifest_type"],
            "luna_execution_setting_history_activation",
        )
        self.assertEqual(manifest["rule_count"], 3)
        self.assertEqual(len(public_safety.LUNA_EXECUTION_SETTING_RULES), 3)
        expected_hash = "50cf6f4f0d41f4097016139cdf3252394680676415022b16c3a9d4b241a68bb5"
        self.assertEqual(manifest["rule_set_sha256"], expected_hash)
        self.assertEqual(
            luna_rule_set_sha256(public_safety.LUNA_EXECUTION_SETTING_RULES),
            expected_hash,
        )
        weakened = public_safety.LUNA_EXECUTION_SETTING_RULES[:-1]
        self.assertNotEqual(luna_rule_set_sha256(weakened), expected_hash)

    def test_luna_history_rejects_identity_split_across_contiguous_added_lines(self):
        commit = "a" * 40

        def additions(start: str, **_kwargs):
            if start == "luna-start":
                return iter(
                    (
                        (commit, "history.txt", 10, "GPT-5.6"),
                        (commit, "history.txt", 11, "Luna Max"),
                    )
                )
            return iter(())

        with (
            mock.patch.object(public_safety, "validate_activation_manifest", return_value={}),
            mock.patch.object(public_safety, "added_lines_since_baseline", return_value=iter(())),
            mock.patch.object(public_safety, "unicode_history_start", return_value=("unicode-start", "fixture")),
            mock.patch.object(public_safety, "luna_history_start", return_value=("luna-start", "fixture")),
            mock.patch.object(public_safety, "uuid_history_start", return_value=("uuid-start", "fixture")),
            mock.patch.object(public_safety, "added_lines_in_range", side_effect=additions),
        ):
            failures = public_safety.history_failures(ROOT)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

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
