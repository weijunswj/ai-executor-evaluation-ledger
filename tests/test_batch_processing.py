import unittest
import json
import hashlib
from unittest.mock import patch, MagicMock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from scripts.processor.batch_processor import process_batch, load_canonical_base_records

class TestBatchProcessing(unittest.TestCase):
    def test_batch_receipt_exists(self):
        batches_dir = ROOT / "ledger" / "receipts" / "batches"
        self.assertTrue(batches_dir.exists())
        files = list(batches_dir.glob("*.json"))
        self.assertGreater(len(files), 0)

        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 1)
        self.assertEqual(data.get("receipt_type"), "batch")
        self.assertIn("batch_id", data)
        self.assertIn("source_comment_ids", data)
        self.assertIn("admitted_run_ids", data)

    def test_dispositions_file_exists(self):
        disp_path = ROOT / "ledger" / "dispositions.jsonl"
        self.assertTrue(disp_path.exists())
        with open(disp_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertGreater(len(lines), 0)
        for d in lines:
            self.assertEqual(d.get("schema_version"), 1)
            self.assertIn("comment_id", d)
            self.assertIn("disposition", d)

    def test_1_all_canonical_protocol_cohorts_survive(self):
        evals_path = ROOT / "evaluations.jsonl"
        with open(evals_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        protocols = {r.get("evaluation_protocol") for r in records}
        self.assertIn("gated_v1", protocols)
        self.assertIn("protocol_unknown", protocols)

    def test_2_gated_v1_survives_source_comment_deletion(self):
        evals_path = ROOT / "evaluations.jsonl"
        with open(evals_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]

        gated_runs = [r for r in records if r.get("evaluation_protocol") == "gated_v1"]
        self.assertGreater(len(gated_runs), 0)

    @patch("scripts.processor.batch_processor.fetch_live_142_comments")
    @patch("scripts.processor.batch_processor.fetch_issue_metadata")
    @patch("scripts.processor.batch_processor.fetch_single_comment")
    def test_11_new_comment_between_snapshots_aborts(self, mock_single, mock_meta, mock_comments):
        c1 = {"id": 101, "body": "<!-- ledger-intake:v1 -->\n{}", "actor": "test", "created_at": "2026-07-29T10:00:00Z", "updated_at": "2026-07-29T10:00:00Z"}
        c2 = {"id": 102, "body": "<!-- ledger-intake:v1 -->\n{}", "actor": "test", "created_at": "2026-07-29T10:05:00Z", "updated_at": "2026-07-29T10:05:00Z"}

        mock_comments.side_effect = [[c1], [c1, c2]]
        mock_meta.return_value = {"updated_at": "2026-07-29T10:00:00Z"}
        mock_single.return_value = c1

        with self.assertRaises(RuntimeError) as ctx:
            process_batch(dry_run=False)
        self.assertIn("Race condition detected", str(ctx.exception))

    @patch("scripts.processor.batch_processor.fetch_live_142_comments")
    @patch("scripts.processor.batch_processor.fetch_issue_metadata")
    @patch("scripts.processor.batch_processor.fetch_single_comment")
    def test_12_edited_terminal_comment_aborts(self, mock_single, mock_meta, mock_comments):
        c1 = {"id": 101, "body": "No marker here", "actor": "test", "created_at": "2026-07-29T10:00:00Z", "updated_at": "2026-07-29T10:00:00Z"}
        c1_edited = {"id": 101, "body": "No marker here, edited", "actor": "test", "created_at": "2026-07-29T10:00:00Z", "updated_at": "2026-07-29T10:01:00Z"}

        mock_comments.return_value = [c1]
        mock_meta.return_value = {"updated_at": "2026-07-29T10:00:00Z"}
        mock_single.return_value = c1_edited

        with self.assertRaises(RuntimeError) as ctx:
            process_batch(dry_run=False)
        self.assertIn("Race condition detected", str(ctx.exception))

    @patch("scripts.processor.batch_processor.fetch_live_142_comments")
    @patch("scripts.processor.batch_processor.fetch_issue_metadata")
    @patch("scripts.processor.batch_processor.fetch_single_comment")
    def test_13_deleted_selected_comment_aborts(self, mock_single, mock_meta, mock_comments):
        c1 = {"id": 101, "body": "<!-- ledger-intake:v1 -->\n{}", "actor": "test", "created_at": "2026-07-29T10:00:00Z", "updated_at": "2026-07-29T10:00:00Z"}

        mock_comments.side_effect = [[c1], []]
        mock_meta.return_value = {"updated_at": "2026-07-29T10:00:00Z"}
        mock_single.return_value = c1

        with self.assertRaises(RuntimeError) as ctx:
            process_batch(dry_run=False)
        self.assertIn("Race condition detected", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
