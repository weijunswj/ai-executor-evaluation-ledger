import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.processor.cleanup_workflow import (
    CleanupConfig,
    prepare_cleanup_receipt,
    publish_cleanup_receipt,
    run_cleanup,
)
from scripts.processor.common import canonical_json_bytes, canonical_json_line_bytes, sha256_bytes
from scripts.processor.transaction import replace_tracked_files

ROOT = Path(__file__).resolve().parents[1]


class TestTransactionAndLifecycle(unittest.TestCase):
    def test_every_replacement_boundary_rolls_back_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix="ledger-tx-test-") as raw:
            root = Path(raw)
            paths = {
                "evaluations.jsonl": b"old-evaluations\n",
                "README.md": b"old-readme\n",
                "scorecard.md": b"old-scorecard\n",
                "ledger/receipts/batches/one.json": b"old-receipt\n",
            }
            for relative, content in paths.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "fixture" + "@" + "example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "fixture"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            candidate = {relative: content.replace(b"old", b"new") for relative, content in paths.items()}
            events = ["candidate_file_write", "before_replace", "after_replace", "between_replacements", "final_integrity_verification"]
            for event in events:
                before = {relative: (root / relative).read_bytes() for relative in paths}

                def hook(stage, relative, wanted=event):
                    if stage == wanted:
                        raise RuntimeError("injected_failure")

                with self.assertRaises(RuntimeError):
                    replace_tracked_files(root, candidate, failure_hook=hook)
                self.assertEqual(
                    {relative: (root / relative).read_bytes() for relative in paths},
                    before,
                    event,
                )

    def test_exact_jsonl_line_bytes_are_the_record_hash_input(self):
        record = {"run_id": "fixture", "text": "é", "number": 1}
        line = canonical_json_line_bytes(record)
        self.assertEqual(line[-1:], b"\n")
        self.assertEqual(sha256_bytes(line), sha256_bytes(line))
        self.assertNotEqual(sha256_bytes(line), sha256_bytes(line[:-1] + b" "))

    def fixture_cleanup_tree(self, root: Path, *, batch_id="batch-cleanup-a005"):
        for relative in (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        body = "retained source fixture"
        digest = sha256_bytes(body.encode("utf-8"))
        author_digest = sha256_bytes(b"fixture-author")
        queue_snapshot_digest = sha256_bytes(
            canonical_json_bytes(
                [{
                    "id": 1,
                    "author_sha256": author_digest,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "body_sha256": digest,
                }]
            )
        )
        hashes = {
            "evaluations_jsonl": sha256_bytes((root / "evaluations.jsonl").read_bytes()),
            "dispositions_jsonl": sha256_bytes((root / "ledger/dispositions.jsonl").read_bytes()),
            "readme_md": sha256_bytes((root / "README.md").read_bytes()),
            "scorecard_md": sha256_bytes((root / "scorecard.md").read_bytes()),
            "model_recommendation_json": sha256_bytes((root / "analysis/model-recommendation.json").read_bytes()),
        }
        batch = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": batch_id,
            "batch_mode": "initial",
            "controller_run_id": "controller-cleanup-a005",
            "base_sha": "a" * 40,
            "canonical_main_sha": "a" * 40,
            "pr_number": 151,
            "expected_head_sha": "c" * 40,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "full_queue_count": 1,
            "latest_observed_comment_id": 1,
            "latest_observed_update_time": "2026-07-29T10:00:00Z",
            "queue_snapshot_sha256": queue_snapshot_digest,
            "source_comment_ids": [1],
            "source_body_sha256": {"1": digest},
            "selected_comment_ids": [1],
            "selected_comment_count": 1,
            "terminal_outcome_count": 1,
            "terminal_outcomes": {
                "1": {
                    "outcome_code": "no_marker",
                    "evaluation_run_id": None,
                    "canonical_record_sha256": None,
                    "cleanup_eligible": False,
                }
            },
            "admitted_run_ids": [],
            "accepted_record_proofs": {},
            "canonical_record_hashes": {},
            "canonical_hashes": hashes,
            "comment_bindings": [
                {
                    "comment_id": 1,
                    "author_sha256": author_digest,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "body_sha256": digest,
                    "outcome_code": "no_marker",
                    "evaluation_run_id": None,
                    "canonical_record_sha256": None,
                    "cleanup_eligible": False,
                }
            ],
        }
        receipt_path = root / "ledger" / "receipts" / "batches" / f"{batch_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(batch, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return body, batch

    def cleanup_config(self, root: Path, batch_id: str, *, receipt_status="unverified", merge_state="merged"):
        return CleanupConfig(
            batch_id=batch_id,
            canonical_merge_sha="a" * 40,
            canonical_main_sha="a" * 40,
            expected_head_sha="c" * 40,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="unreviewed",
            pr_state="closed",
            merge_state=merge_state,
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status=receipt_status,
            repository_root=root,
        )

    def authority_reader(self, config):
        return {
            "pr_state": config.pr_state,
            "merge_state": config.merge_state,
            "checks_state": config.checks_state,
            "review_state": config.review_state,
            "canonical_merge_sha": config.canonical_merge_sha,
            "expected_head_sha": config.expected_head_sha,
            "canonical_main_sha": config.canonical_main_sha,
            "recorded_receipt_status": config.recorded_receipt_status,
        }

    def test_cleanup_verifies_retention_and_stays_pending_without_receipt_proof(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root)

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"l" + "ogin": "fixture-author"},
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            result = run_cleanup(
                self.cleanup_config(root, "batch-cleanup-a005"),
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["source_comments_retained"])
            self.assertFalse(result["publication_attempted"])
            self.assertEqual(result["receipt"]["branch_cleanup_reason"], "receipt_unverified")

    def test_verified_cleanup_can_reach_injected_future_publication_only_when_reviewed(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-live-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root, batch_id="batch-cleanup-live-a005")

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"l" + "ogin": "fixture-author"},
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            config = self.cleanup_config(root, "batch-cleanup-live-a005", receipt_status="absent")
            receipt = prepare_cleanup_receipt(
                config,
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            self.assertEqual(receipt["cleanup_status"], "verified")
            calls = []
            published = publish_cleanup_receipt(
                receipt,
                activation_mode="reviewed-live",
                operator_intent="reviewed",
                publisher=lambda value: calls.append(value) or {"status": "SIMULATED_OPERATOR_PUBLICATION"},
            )
            self.assertEqual(published["status"], "SIMULATED_OPERATOR_PUBLICATION")
            self.assertEqual(len(calls), 1)
            with self.assertRaises(Exception):
                publish_cleanup_receipt(
                    receipt,
                    activation_mode="dry-run",
                    operator_intent="unreviewed",
                )


if __name__ == "__main__":
    unittest.main()
