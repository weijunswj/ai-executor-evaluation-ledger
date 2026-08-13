from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import jsonschema

from scripts.validate_manifests import (
    MANIFEST_PATHS,
    ManifestValidationError,
    TARGET_EVALUATIONS_SHA,
    expected_manifests,
    validate_all,
    validate_correction_records,
    validate_manifest_documents,
)
from scripts.rebuild_views import verify_append_only
from scripts.validate_manifests import _locked_historical_final_raw

ROOT = Path(__file__).resolve().parents[1]
FUTURE_BASE = "9b95cd37f746846d31bc0dfc5f3d79e8e2de75de"


class TestClosedManifestValidation(unittest.TestCase):
    def schema(self):
        return json.loads(
            (ROOT / "schema" / "manifest.schema.json").read_text(encoding="utf-8")
        )

    def actual(self):
        return {
            name: json.loads(
                (ROOT / "migrations" / name).read_text(encoding="utf-8")
            )
            for name in MANIFEST_PATHS
        }

    def test_repository_wide_manifest_validation(self):
        evidence = validate_all(ROOT, base_ref=FUTURE_BASE)
        self.assertEqual(evidence["manifest_count"], len(MANIFEST_PATHS))
        self.assertEqual(evidence["final_total_count"], 59)

    def test_evaluations_have_one_canonical_lf_checkout_contract(self):
        attributes = (
            ROOT / ".gitattributes"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            1,
            attributes.count("evaluations.jsonl text eol=lf"),
        )
        attribute_result = subprocess.run(
            ["git", "check-attr", "eol", "--", "evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            "evaluations.jsonl: eol: lf",
            attribute_result.stdout.strip(),
        )
        checkout = (ROOT / "evaluations.jsonl").read_bytes()
        self.assertNotIn(b"\r\n", checkout)
        historical_prefix = subprocess.run(
            ["git", "show", f"{FUTURE_BASE}:evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(TARGET_EVALUATIONS_SHA, hashlib.sha256(historical_prefix).hexdigest())
        self.assertTrue(checkout.startswith(historical_prefix))

    def test_append_only_verifier_accepts_closed_manifest_contract(self):
        verify_append_only(FUTURE_BASE)

    def test_unknown_field_fails_closed_schema(self):
        expected = expected_manifests(ROOT)
        corrupted = copy.deepcopy(expected)
        corrupted["preservation-manifest.json"]["unexpected"] = True
        with self.assertRaises(ManifestValidationError):
            validate_manifest_documents(corrupted, expected, self.schema())

    def test_unicode_activation_unknown_field_fails_closed_schema(self):
        expected = expected_manifests(ROOT)
        corrupted = copy.deepcopy(expected)
        corrupted["unicode-identity-history-activation.json"][
            "unexpected"
        ] = True
        with self.assertRaises(ManifestValidationError):
            validate_manifest_documents(corrupted, expected, self.schema())

    def test_count_corruption_fails_exact_reconciliation(self):
        expected = expected_manifests(ROOT)
        corrupted = copy.deepcopy(expected)
        corrupted["preservation-manifest.json"]["final_total_count"] += 1
        with self.assertRaises(ManifestValidationError):
            validate_manifest_documents(corrupted, expected, self.schema())

    def test_hash_corruption_fails_exact_binding(self):
        expected = expected_manifests(ROOT)
        corrupted = copy.deepcopy(expected)
        corrupted["base-model-v2.json"]["after_sha256"] = "0" * 64
        with self.assertRaises(ManifestValidationError):
            validate_manifest_documents(corrupted, expected, self.schema())

    def test_schema_is_closed_and_every_type_is_exact(self):
        schema = self.schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        expected = expected_manifests(ROOT)
        validate_manifest_documents(expected, expected, schema)
        self.assertEqual(
            {value["manifest_type"] for value in expected.values()},
            set(MANIFEST_PATHS.values()),
        )


    def assert_correction_mutation_rejected(self, mutate):
        path = ROOT / "migrations" / "correction-records-v3.jsonl"
        original = path.read_bytes()
        records = [
            json.loads(line)
            for line in original.decode("utf-8").splitlines()
            if line.strip()
        ]
        try:
            mutate(records)
            path.write_bytes(
                b"".join(
                    (
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    for record in records
                )
            )
            with self.assertRaises(ManifestValidationError):
                validate_correction_records(ROOT)
        finally:
            path.write_bytes(original)

    def test_correction_proofs_bind_all_locked_records(self):
        evidence = validate_correction_records(
            ROOT,
            final_raw=_locked_historical_final_raw(ROOT),
        )
        self.assertEqual(evidence["record_count"], 116)
        self.assertEqual(evidence["proofs_checked"], 116)
        self.assertEqual(evidence["before_proofs_recomputed"], 116)
        self.assertEqual(evidence["after_proofs_recomputed"], 106)
        self.assertEqual(evidence["withdrawal_absence_checks"], 10)
        self.assertEqual(
            evidence["counts"],
            {
                "authority_gap": 59,
                "public_safe_redaction": 25,
                "factual_correction": 19,
                "withdrawal": 10,
                "base_model_replacement": 3,
            },
        )
        rows = [
            json.loads(line)
            for line in _locked_historical_final_raw(ROOT).decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(
            all(
                isinstance(row["weighted_score_5"], (int, float))
                and isinstance(row["weighted_score_10"], (int, float))
                for row in rows
            )
        )

    def test_each_correction_proof_hash_and_length_corruption_fails_closed(self):
        mutations = {
            "before_sha256": lambda records: records[0]["before"].update(sha256="0" * 64),
            "before_byte_length": lambda records: records[0]["before"].update(byte_length=1),
            "after_sha256": lambda records: records[0]["after"].update(sha256="0" * 64),
            "after_byte_length": lambda records: records[0]["after"].update(byte_length=1),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.assert_correction_mutation_rejected(mutate)

    def test_string_score_drift_fails_closed(self):
        path = ROOT / "evaluations.jsonl"
        original = path.read_bytes()
        rows = [
            json.loads(line)
            for line in original.decode("utf-8").splitlines()
            if line.strip()
        ]
        for row in rows:
            row["weighted_score_5"] = str(row["weighted_score_5"])
            row["weighted_score_10"] = str(row["weighted_score_10"])
        try:
            path.write_bytes(
                b"".join(
                    (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                    for row in rows
                )
            )
            with self.assertRaises(ManifestValidationError):
                validate_correction_records(ROOT)
        finally:
            path.write_bytes(original)

    def test_withdrawal_and_replacement_membership_fail_closed(self):
        def corrupt_withdrawal(records):
            record = next(item for item in records if item["record_type"] == "withdrawal")
            record["target"]["original_record_sha256"] = "0" * 64

        def corrupt_replacement(records):
            record = next(item for item in records if item["record_type"] == "base_model_replacement")
            record["replacement"]["replacement_run_id"] = "subject-" + "0" * 64

        self.assert_correction_mutation_rejected(corrupt_withdrawal)
        self.assert_correction_mutation_rejected(corrupt_replacement)

    def test_lineage_hash_chain_and_order_corruption_fail_closed(self):
        self.assert_correction_mutation_rejected(
            lambda records: records[0]["lineage"].update(correction_sha256="0" * 64)
        )
        self.assert_correction_mutation_rejected(
            lambda records: records[1]["lineage"].update(prior_correction_sha256="0" * 64)
        )

        def swap_records(records):
            records[0], records[1] = records[1], records[0]

        self.assert_correction_mutation_rejected(swap_records)


if __name__ == "__main__":
    unittest.main()
