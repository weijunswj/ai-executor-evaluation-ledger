import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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

if __name__ == "__main__":
    unittest.main()
