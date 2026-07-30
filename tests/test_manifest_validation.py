from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from scripts.validate_manifests import (
    MANIFEST_PATHS,
    ManifestValidationError,
    expected_manifests,
    validate_all,
    validate_manifest_documents,
)

ROOT = Path(__file__).resolve().parents[1]


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
        evidence = validate_all(ROOT)
        self.assertEqual(evidence["manifest_count"], len(MANIFEST_PATHS))
        self.assertEqual(evidence["final_total_count"], 138)

    def test_unknown_field_fails_closed_schema(self):
        expected = expected_manifests(ROOT)
        corrupted = copy.deepcopy(expected)
        corrupted["preservation-manifest.json"]["unexpected"] = True
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


if __name__ == "__main__":
    unittest.main()
