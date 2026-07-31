from __future__ import annotations

import copy
import json
import os
import subprocess
import unittest
from pathlib import Path

from scripts.processor.batch_processor import fetch_live_142_comments
from scripts.processor.frozen_replay import (
    migrate_canonical_base,
    replay_frozen_from_receipt,
)

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
