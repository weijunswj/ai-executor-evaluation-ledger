import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.processor.common import canonical_json_line_bytes, sha256_bytes
from scripts.seal_batch_receipt import build_sealed_receipt
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    _load_schema,
    _parse_batch,
    validate_all_tracked_batch_receipts,
    validate_batch_receipt_object,
)

ROOT = Path(__file__).resolve().parents[1]


class TestReceiptValidation(unittest.TestCase):
    def test_frozen_draft_migrates_without_identity_or_rejection_prose(self):
        tracked = json.loads(
            (
                ROOT
                / "ledger/receipts/batches/batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        candidate_sha = tracked.get("candidate_content_commit_sha")
        if candidate_sha is None:
            candidate_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        receipt = build_sealed_receipt(
            ROOT,
            candidate_content_commit_sha=candidate_sha,
        )
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["full_queue_count"], 101)
        self.assertEqual(receipt["selected_comment_count"], 101)
        self.assertEqual(receipt["terminal_outcome_count"], 101)
        self.assertEqual(len(receipt["admitted_run_ids"]), 79)
        encoded = json.dumps(receipt, sort_keys=True)
        for forbidden in (
            '"author"',
            "author_sha256",
            '"reason"',
            "pending_reason",
            "PENDING_CONTROLLER_ACTION",
            "owner_withdrawn",
        ):
            self.assertNotIn(forbidden, encoded)

    def fixture(self, root: Path, *, extra_final_file=False):
        record = {
            "run_id": "run-receipt-fixture",
            "provider": "OpenAI",
            "model": "GPT-5.6 Sol",
            "outcome": "accepted",
            "weighted_score_5": 4.5,
        }
        record_line = canonical_json_line_bytes(record)
        contents = {
            "evaluations.jsonl": record_line,
            "ledger/dispositions.jsonl": b"",
            "README.md": b"# fixture\n",
            "scorecard.md": b"# fixture\n",
            "analysis/model-recommendation.json": b"{}\n",
        }
        for relative, content in contents.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        schema_target = root / "schema/receipt.schema.json"
        schema_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "schema/receipt.schema.json", schema_target)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture" + "@" + "example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "fixture"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "content"], cwd=root, check=True)
        content_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        digest = sha256_bytes(b"source")
        receipt = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": "batch-receipt-fixture",
            "batch_mode": "initial",
            "controller_run_id": "controller-receipt-fixture",
            "base_sha": content_sha,
            "canonical_main_sha": content_sha,
            "candidate_content_commit_sha": content_sha,
            "pr_number": 151,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "source_comment_watermark": 1,
            "full_queue_count": 1,
            "latest_observed_comment_id": 1,
            "latest_observed_update_time": "2026-07-29T10:00:00Z",
            "queue_snapshot_sha256": digest,
            "source_comment_ids": [1],
            "source_body_sha256": {"1": digest},
            "selected_comment_ids": [1],
            "selected_comment_count": 1,
            "terminal_outcome_count": 1,
            "terminal_outcomes": {
                "1": {
                    "outcome_code": "admitted",
                    "evaluation_run_id": record["run_id"],
                    "canonical_record_sha256": sha256_bytes(record_line),
                    "cleanup_eligible": True,
                }
            },
            "admitted_run_ids": [record["run_id"]],
            "accepted_record_proofs": {
                record["run_id"]: {
                    "provider": record["provider"],
                    "model": record["model"],
                    "outcome": record["outcome"],
                    "weighted_score_5": record["weighted_score_5"],
                }
            },
            "canonical_record_hashes": {
                record["run_id"]: sha256_bytes(record_line)
            },
            "canonical_hashes": {
                name: sha256_bytes(contents[relative])
                for name, relative in CANONICAL_PATHS.items()
            },
            "comment_bindings": [
                {
                    "comment_id": 1,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "body_sha256": digest,
                    "outcome_code": "admitted",
                    "evaluation_run_id": record["run_id"],
                    "canonical_record_sha256": sha256_bytes(record_line),
                    "cleanup_eligible": True,
                }
            ],
        }
        receipt_path = root / "ledger/receipts/batches/batch-receipt-fixture.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if extra_final_file:
            (root / "extra.txt").write_text("extra\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "receipt"], cwd=root, check=True)
        final_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return receipt, content_sha, final_sha

    def test_pr_and_canonical_main_modes_validate_immutable_bytes(self):
        with tempfile.TemporaryDirectory(prefix="receipt-validator-") as raw:
            root = Path(raw)
            _receipt, _content_sha, final_sha = self.fixture(root)
            pr = validate_all_tracked_batch_receipts(
                root,
                authority_sha=final_sha,
                mode="pr",
            )
            self.assertEqual(pr["final_parent_sha"], _content_sha)
            canonical = validate_all_tracked_batch_receipts(
                root,
                authority_sha=final_sha,
                mode="canonical-main",
            )
            self.assertEqual(canonical["receipt_count"], 1)

    def test_each_aggregate_and_record_hash_is_independently_enforced(self):
        with tempfile.TemporaryDirectory(prefix="receipt-hash-test-") as raw:
            root = Path(raw)
            receipt, _content_sha, final_sha = self.fixture(root)
            for hash_name in CANONICAL_PATHS:
                corrupt = copy.deepcopy(receipt)
                corrupt["canonical_hashes"][hash_name] = "0" * 64
                with self.assertRaises(ReceiptValidationError, msg=hash_name):
                    validate_batch_receipt_object(
                        root,
                        corrupt,
                        authority_sha=final_sha,
                    )
            corrupt = copy.deepcopy(receipt)
            corrupt["canonical_record_hashes"]["run-receipt-fixture"] = "0" * 64
            with self.assertRaises(ReceiptValidationError):
                validate_batch_receipt_object(
                    root,
                    corrupt,
                    authority_sha=final_sha,
                )

    def test_legacy_author_fields_and_unknown_outcomes_fail_closed(self):
        schema = _load_schema(ROOT)
        with self.assertRaises(ReceiptValidationError):
            _parse_batch(
                json.dumps(
                    {
                        "schema_version": 1,
                        "receipt_type": "batch",
                    }
                ).encode("utf-8"),
                schema,
            )
        with tempfile.TemporaryDirectory(prefix="receipt-schema-test-") as raw:
            root = Path(raw)
            receipt, _content_sha, _final_sha = self.fixture(root)
            for field, value in (
                ("author", "fixture"),
                ("author_sha256", "a" * 64),
                ("reason", "fixture"),
            ):
                corrupt = copy.deepcopy(receipt)
                corrupt["comment_bindings"][0][field] = value
                with self.assertRaises(ReceiptValidationError, msg=field):
                    _parse_batch(
                        (json.dumps(corrupt) + "\n").encode("utf-8"),
                        schema,
                    )
            corrupt = copy.deepcopy(receipt)
            corrupt["terminal_outcomes"]["1"]["outcome_code"] = "unbounded"
            with self.assertRaises(ReceiptValidationError):
                _parse_batch((json.dumps(corrupt) + "\n").encode("utf-8"), schema)

    def test_pr_mode_requires_receipt_only_single_parent_final_commit(self):
        with tempfile.TemporaryDirectory(prefix="receipt-scope-test-") as raw:
            root = Path(raw)
            _receipt, _content_sha, final_sha = self.fixture(
                root,
                extra_final_file=True,
            )
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(
                    root,
                    authority_sha=final_sha,
                    mode="pr",
                )


if __name__ == "__main__":
    unittest.main()
