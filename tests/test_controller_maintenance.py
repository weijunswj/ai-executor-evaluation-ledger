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
        expected_hash = "50cf6f4f49f8b43876ef07fa88bda745d9c0b2cbcf1359a60eead3baa8a68bb5"
        self.assertEqual(manifest["rule_set_sha256"], expected_hash)
        self.assertEqual(
            luna_rule_set_sha256(public_safety.LUNA_EXECUTION_SETTING_RULES),
            expected_hash,
        )
        weakened = public_safety.LUNA_EXECUTION_SETTING_RULES[:-1]
        self.assertNotEqual(luna_rule_set_sha256(weakened), expected_hash)

    def test_luna_tdd_history_exceptions_are_exact(self):
        self.assertEqual(
            public_safety.LUNA_TDD_HISTORY_ALLOWED_MATCHES,
            frozenset(
                {
                    (
                        "ba224fb72dd9e10fd65d36fdbd33f2974679f8ce",
                        "tests/test_controller_maintenance.py",
                        270,
                        "luna_execution_setting_003",
                    ),
                    (
                        "6e0ec65979831e720680d0c7633ec9c427e2cceb",
                        "tests/test_controller_maintenance.py",
                        242,
                        "luna_execution_setting_003",
                    ),
                }
            ),
        )

    def test_luna_history_rejects_identity_split_across_contiguous_added_lines(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-added-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed safe history")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "add split identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_luna_history_rejects_added_line_with_unchanged_neighbor_context(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-context-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed setting fragment")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "add neighbouring model fragment")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_luna_history_ignores_unrelated_preexisting_identity(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-existing-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                model_line + "\n" + setting_line + "\nsafe\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed existing identity")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                model_line + "\n" + setting_line + "\nsafe changed\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "change unrelated context")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertEqual([], failures)

    def test_luna_history_detects_deletion_only_introduction(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-delete-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                model_line + "\nseparator\n" + setting_line + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed separated fragments")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "delete separator only")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_luna_history_rejects_relocated_occurrence_with_equal_count(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-relocation-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed grandfathered occurrence")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "header\nsafe middle\nfooter\n"
                + model_line
                + "\n"
                + setting_line
                + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "relocate occurrence without changing count")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove relocated occurrence")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_luna_history_allows_continuously_inherited_line_shifts(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-line-shift-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed inherited occurrence")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "header\nunrelated insertion\n"
                + model_line
                + "\n"
                + setting_line
                + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "shift occurrence down")

            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove unrelated insertion")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertEqual([], failures)

    def test_oversized_jsonl_still_rejects_luna_execution_setting(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting = " ".join(("Luna", "Max"))
        identity = model_line + " " + setting
        with tempfile.TemporaryDirectory(prefix="ledger-large-jsonl-") as temp_raw:
            root = Path(temp_raw)
            path = root / "evaluations.jsonl"
            record = {
                "note": "x" * (public_safety.MAX_TEXT_BYTES + 64) + " " + identity,
            }
            path.write_text(
                json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_jsonl_object_keys_are_scanned_in_live_and_history(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        identity = model_fragment + " " + setting_fragment

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-key-context-") as temp_raw:
            root = Path(temp_raw)
            complete_key = root / "complete.jsonl"
            complete_key.write_text(
                json.dumps({identity: "safe"}) + "\n",
                encoding="utf-8",
            )
            complete_failures = public_safety.scan_jsonl(complete_key, root=root)
            self.assertTrue(
                any("luna_execution_setting" in failure for failure in complete_failures),
                complete_failures,
            )

            split_context = root / "split.jsonl"
            split_context.write_text(
                json.dumps({model_fragment: setting_fragment}) + "\n",
                encoding="utf-8",
            )
            split_failures = public_safety.scan_jsonl(split_context, root=root)
            self.assertTrue(
                any("luna_execution_setting" in failure for failure in split_failures),
                split_failures,
            )

            safe_keys = root / "safe.jsonl"
            safe_keys.write_text(
                json.dumps({"safe-key": "safe-value"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual([], public_safety.scan_jsonl(safe_keys, root=root))

            sensitive_key = root / "sensitive.jsonl"
            sensitive_key.write_text(
                json.dumps({"repository": "safe"}) + "\n",
                encoding="utf-8",
            )
            sensitive_failures = public_safety.scan_jsonl(sensitive_key, root=root)
            self.assertTrue(
                any("forbidden JSON key" in failure for failure in sensitive_failures),
                sensitive_failures,
            )

            history = root / "evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "seed safe JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                json.dumps({identity: "safe"}) + "\n",
                encoding="utf-8",
            )
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "introduce transient key identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "remove transient key identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
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

    def test_red_jsonl_duplicate_keys_fail_live_oversized_and_historical(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        identity = model_fragment + " " + setting_fragment
        duplicate_record = (
            '{"note":'
            + json.dumps(identity)
            + ',"note":"safe"}\n'
        ).encode("utf-8")
        nested_duplicate_record = b'{"outer":{"safe":"one","safe":"two"}}\n'

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-duplicate-keys-") as temp_raw:
            root = Path(temp_raw)
            live = root / "live.jsonl"
            live.write_bytes(duplicate_record + nested_duplicate_record)
            live_failures = public_safety.scan_jsonl(live, root=root)
            self.assertEqual(
                2,
                sum("duplicate object keys" in failure for failure in live_failures),
                live_failures,
            )
            self.assertTrue(
                all(identity not in failure for failure in live_failures),
                live_failures,
            )

            oversized_root = root / "oversized"
            oversized_root.mkdir()
            oversized_record = (
                '{"padding":"'
                + ("x" * (public_safety.MAX_TEXT_BYTES + 64))
                + '","note":'
                + json.dumps(identity)
                + ',"note":"safe"}\n'
            ).encode("utf-8")
            oversized_path = oversized_root / "evaluations.jsonl"
            oversized_path.write_bytes(oversized_record)
            self.assertGreater(oversized_path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            oversized_failures = public_safety.tree_failures(oversized_root)
            self.assertTrue(
                any("duplicate object keys" in failure for failure in oversized_failures),
                oversized_failures,
            )

            history = root / "historical-evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "seed historical JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_bytes(duplicate_record)
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "introduce duplicate JSONL key")
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "remove duplicate JSONL key")
            end = git(root, "rev-parse", "HEAD")

            with self.assertRaisesRegex(RuntimeError, "invalid text") as context:
                public_safety.luna_history_failures_in_range(
                    start,
                    end=end,
                    root=root,
                )

        self.assertNotIn(identity, str(context.exception))

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


    def test_red_oversized_jsonl_preserves_cross_value_luna_context(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        record = {
            "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
            "parts": [model_fragment, setting_fragment],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "evaluations.jsonl"
            jsonl.write_text(json.dumps(record) + "\n", encoding="utf-8")
            self.assertGreater(jsonl.stat().st_size, public_safety.MAX_TEXT_BYTES)

            failures = public_safety.tree_failures(root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_luna_history_merge_only_introduction_is_not_missed(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            history = root / "history.txt"
            history.write_text("base-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            git(root, "checkout", "-qb", "feature")
            history.write_text("feature-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "feature")

            git(root, "checkout", "-q", "main")
            history.write_text("main-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "main divergence")

            merge_result = subprocess.run(
                ["git", "merge", "--no-ff", "--no-commit", "feature"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(merge_result.returncode, 0)
            history.write_text(
                model_fragment + "\n" + setting_fragment + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "merge resolution")
            introduced = git(root, "rev-parse", "HEAD").strip()
            parents = git(root, "show", "-s", "--format=%P", introduced).split()
            self.assertEqual(len(parents), 2)

            history.write_text("safe-after-delete\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "delete transient identity")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertTrue(
            any(introduced[:12] in failure and "luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_safe_oversized_jsonl_history_is_processed_incrementally(self):
        safe_record = {"note": "x" * (public_safety.MAX_TEXT_BYTES + 64)}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            jsonl = root / "evaluations.jsonl"
            jsonl.write_text('{"note":"base-safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe_record) + "\n")
            self.assertGreater(jsonl.stat().st_size, public_safety.MAX_TEXT_BYTES)
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "safe oversized append")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertEqual([], failures)

    def test_red_unsafe_oversized_jsonl_history_remains_detectable(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        unsafe_record = {
            "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
            "parts": [model_fragment, setting_fragment],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            jsonl = root / "evaluations.jsonl"
            jsonl.write_text('{"note":"base-safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(unsafe_record) + "\n")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "unsafe oversized append")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )


if __name__ == "__main__":
    unittest.main()
