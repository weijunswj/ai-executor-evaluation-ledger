from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_controller_maintenance_scope_is_exact_four_files(self):
        required = {
            ".github/workflows/ci.yml",
            ".github/workflows/public-safety.yml",
            "scripts/validate_receipts.py",
            "tests/test_controller_maintenance.py",
        }
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/ledger-maintenance-*', workflow)
                self.assertIn('git diff --name-only "$BASE_SHA" "$HEAD_SHA"', workflow)
                self.assertIn("legacy_context=true", workflow)
                for path in required:
                    self.assertIn(path, workflow)

    def test_main_push_requires_frozen_receipt_bytes_unchanged(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(
                'git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- ledger/receipts/batches',
                workflow,
            )

    def test_controller_lanes_run_suite_under_bounded_legacy_context(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("GITHUB_EVENT_NAME=push GITHUB_REF_NAME=main python -m unittest", workflow)
            self.assertIn("controller/evaluation-*", workflow)
            self.assertIn("controller/ledger-maintenance-*", workflow)

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
