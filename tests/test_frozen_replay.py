from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from scripts.processor.batch_processor import fetch_live_142_comments
from scripts.processor.frozen_replay import (
    FrozenBatchPolicy,
    VerifiedFrozenSource,
    migrate_canonical_base,
    replay_frozen_batch,
    replay_frozen_from_receipt,
)
from scripts.validate_manifests import TARGET_EVALUATIONS_SHA

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    ROOT
    / "ledger"
    / "receipts"
    / "batches"
    / "batch-20260729-gate3-amendment-004.json"
)
CANONICAL_MAIN = "27748b1fa4b70eb69f18047c31ec97c3505beb88"


def git_object(revision: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


class TestFrozenReplay(unittest.TestCase):
    def test_closed_canonical_base_migration_is_deterministic(self):
        source = git_object(CANONICAL_MAIN, "evaluations.jsonl")
        first_records, first_bytes = migrate_canonical_base(source)
        second_records, second_bytes = migrate_canonical_base(source)
        self.assertEqual(first_records, second_records)
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(len(first_records), 59)
        self.assertEqual(
            len({record["run_id"] for record in first_records}),
            59,
        )
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), TARGET_EVALUATIONS_SHA)
    def test_frozen_replay_binds_migration_manifest_to_frozen_dispositions(self):
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        policy = FrozenBatchPolicy.from_receipt(receipt)
        bindings = receipt["comment_bindings"]
        fingerprints = tuple(
            {
                "id": binding["comment_id"],
                "created_at": binding["created_at"],
                "updated_at": binding["updated_at"],
                "body_sha256": binding["body_sha256"],
            }
            for binding in bindings
        )
        source = VerifiedFrozenSource(
            comments=tuple({"body": ""} for _binding in bindings),
            fingerprints=fingerprints,
            snapshot_sha256=receipt["queue_snapshot_sha256"],
            later_comment_count=0,
        )
        canonical_source = git_object(
            policy.canonical_base_sha,
            "evaluations.jsonl",
        )
        base_records, base_bytes = migrate_canonical_base(canonical_source)
        dispositions_result = subprocess.run(
            [
                "git",
                "show",
                f"{policy.canonical_base_sha}:ledger/dispositions.jsonl",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        existing_dispositions = dispositions_result.stdout
        replay = replay_frozen_batch(
            ROOT,
            canonical_base_sha=policy.canonical_base_sha,
            batch_id=policy.batch_id,
            policy=policy,
            verified_source=source,
            existing_canonical_base_records=base_records,
            existing_canonical_base_bytes=base_bytes,
            canonical_source_base_bytes=canonical_source,
            existing_dispositions_bytes=existing_dispositions,
            canonical_base_readme_bytes=git_object(
                policy.canonical_base_sha,
                "README.md",
            ),
            canonical_base_scorecard_bytes=git_object(
                policy.canonical_base_sha,
                "scorecard.md",
            ),
        )
        frozen_dispositions = replay.candidate_files[
            "ledger/dispositions.jsonl"
        ]
        manifest = json.loads(
            replay.candidate_files[
                "migrations/correction-migration-manifest.json"
            ].decode("utf-8")
        )
        self.assertEqual(
            manifest["candidate_dispositions_sha256"],
            hashlib.sha256(frozen_dispositions).hexdigest(),
        )
        self.assertNotEqual(
            manifest["candidate_dispositions_sha256"],
            hashlib.sha256(
                (ROOT / "ledger" / "dispositions.jsonl").read_bytes()
            ).hexdigest(),
        )

    @unittest.skipUnless(
        os.environ.get("LEDGER_RUN_SOURCE_REPLAY_TESTS") == "1",
        "live frozen-source replay is exercised by the required source mode",
    )
    def test_live_replay_is_deterministic_and_ignores_prior_outcomes(self):
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        comments = fetch_live_142_comments(ROOT)
        first = replay_frozen_from_receipt(ROOT, receipt, comments)
        second = replay_frozen_from_receipt(ROOT, receipt, comments)
        self.assertEqual(first.candidate_files, second.candidate_files)
        self.assertEqual(first.terminal_outcomes, second.terminal_outcomes)
        self.assertEqual(len(first.terminal_outcomes), 101)

        superseded = copy.deepcopy(receipt)
        for outcome in superseded["terminal_outcomes"].values():
            outcome["outcome_code"] = "no_marker"
            outcome["evaluation_run_id"] = None
            outcome["canonical_record_sha256"] = None
        superseded["admitted_run_ids"] = []
        superseded["accepted_record_proofs"] = {}
        superseded["canonical_record_hashes"] = {}
        replayed = replay_frozen_from_receipt(
            ROOT,
            superseded,
            comments,
        )
        self.assertEqual(first.terminal_outcomes, replayed.terminal_outcomes)
        self.assertEqual(first.admitted_run_ids, replayed.admitted_run_ids)
        for relative_path, expected in first.candidate_files.items():
            self.assertEqual(
                (ROOT / relative_path).read_bytes(),
                expected,
                relative_path,
            )


if __name__ == "__main__":
    unittest.main()
