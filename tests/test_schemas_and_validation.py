import unittest
import json
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[1]

class TestSchemasAndValidation(unittest.TestCase):
    def setUp(self):
        with open(ROOT / "schema" / "evaluation.schema.json", "r", encoding="utf-8") as f:
            self.eval_schema = json.load(f)
        with open(ROOT / "schema" / "intake.schema.json", "r", encoding="utf-8") as f:
            self.intake_schema = json.load(f)
        with open(ROOT / "schema" / "receipt.schema.json", "r", encoding="utf-8") as f:
            self.receipt_schema = json.load(f)
        with open(ROOT / "schema" / "disposition.schema.json", "r", encoding="utf-8") as f:
            self.disp_schema = json.load(f)

    def test_schema_files_valid_draft202012(self):
        for schema in [self.eval_schema, self.intake_schema, self.receipt_schema, self.disp_schema]:
            self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")

    def test_evaluations_jsonl_conforms_to_schema(self):
        evals_file = ROOT / "evaluations.jsonl"
        self.assertTrue(evals_file.exists())
        with open(evals_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertGreater(len(lines), 0)
        for idx, line in enumerate(lines, start=1):
            record = json.loads(line)
            try:
                jsonschema.validate(instance=record, schema=self.eval_schema)
            except jsonschema.ValidationError as ve:
                self.fail(f"evaluations.jsonl:{idx} failed schema validation: {ve.message}")

    def test_dispositions_jsonl_conforms_to_schema(self):
        disp_file = ROOT / "ledger" / "dispositions.jsonl"
        if not disp_file.exists():
            return
        with open(disp_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        for idx, line in enumerate(lines, start=1):
            record = json.loads(line)
            try:
                jsonschema.validate(instance=record, schema=self.disp_schema)
            except jsonschema.ValidationError as ve:
                self.fail(f"dispositions.jsonl:{idx} failed schema validation: {ve.message}")

    def test_batch_receipt_conforms_to_schema(self):
        batches_dir = ROOT / "ledger" / "receipts" / "batches"
        if not batches_dir.exists():
            return
        for bfile in batches_dir.glob("*.json"):
            data = json.loads(bfile.read_text(encoding="utf-8"))
            try:
                jsonschema.validate(instance=data, schema=self.receipt_schema)
            except jsonschema.ValidationError as ve:
                self.fail(f"{bfile.name} failed schema validation: {ve.message}")

if __name__ == "__main__":
    unittest.main()
