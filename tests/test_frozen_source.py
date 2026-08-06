from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from scripts.processor.common import (
    ProcessorError,
    canonical_json_bytes,
)
from scripts.processor.frozen_source import refetch_frozen_source

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = json.loads(
    (
        ROOT
        / "ledger"
        / "receipts"
        / "batches"
        / "batch-20260729-gate3-amendment-004.json"
    ).read_text(encoding="utf-8")
)


class TestFrozenSourceAuthority(unittest.TestCase):
    def queue(self):
        by_id = {
            binding["comment_id"]: binding
            for binding in RECEIPT["comment_bindings"]
        }
        non_ascii = bytes([195, 169]).decode("utf-8", errors="strict")
        author_field = bytes([108, 111, 103, 105, 110]).decode("ascii")
        comments = [
            {
                "id": comment_id,
                "user": {author_field: "fixture-author"},
                "body": (
                    "genuine-" + non_ascii
                    if index == 0
                    else f"fixture-{comment_id}"
                ),
                "created_at": by_id[comment_id]["created_at"],
                "updated_at": by_id[comment_id]["updated_at"],
            }
            for index, comment_id in enumerate(RECEIPT["source_comment_ids"])
        ]
        comments.append(
            {
                "id": 9999999999,
                "user": {author_field: "later-author"},
                "body": "later",
                "created_at": "2026-07-30T00:00:00Z",
                "updated_at": "2026-07-30T00:00:00Z",
            }
        )
        return comments

    def authority(self):
        queue = self.queue()
        receipt = copy.deepcopy(RECEIPT)
        selected = queue[: len(receipt["source_comment_ids"])]
        fingerprints = []
        hashes = {}
        bindings = {
            binding["comment_id"]: binding
            for binding in receipt["comment_bindings"]
        }
        for comment in selected:
            body_hash = hashlib.sha256(
                comment["body"].encode("utf-8")
            ).hexdigest()
            hashes[str(comment["id"])] = body_hash
            bindings[comment["id"]]["body_sha256"] = body_hash
            fingerprints.append(
                {
                    "id": comment["id"],
                    "author_sha256": hashlib.sha256(
                        comment["user"]["login"].encode("utf-8")
                    ).hexdigest(),
                    "created_at": comment["created_at"],
                    "updated_at": comment["updated_at"],
                    "body_sha256": body_hash,
                }
            )
        snapshot = hashlib.sha256(
            canonical_json_bytes(fingerprints)
        ).hexdigest()
        receipt["source_body_sha256"] = hashes
        receipt["queue_snapshot_sha256"] = snapshot
        return receipt, queue, snapshot

    def test_exact_membership_non_ascii_hash_and_later_exclusion(self):
        receipt, queue, snapshot = self.authority()
        with mock.patch(
            "scripts.processor.frozen_replay.FROZEN_SNAPSHOT_SHA256",
            snapshot,
        ):
            evidence = refetch_frozen_source(
                ROOT,
                receipt,
                queue_fetcher=lambda _root: copy.deepcopy(queue),
            )
        self.assertEqual(len(evidence["fingerprints"]), 101)
        self.assertEqual(evidence["later_comment_count"], 1)
        self.assertNotIn("9999999999", evidence["source_body_sha256"])
        first = receipt["source_comment_ids"][0]
        expected = hashlib.sha256(
            queue[0]["body"].encode("utf-8", errors="strict")
        ).hexdigest()
        self.assertEqual(evidence["source_body_sha256"][str(first)], expected)

    def test_moved_timestamp_or_missing_member_fails_closed(self):
        receipt, queue, snapshot = self.authority()
        moved = copy.deepcopy(queue)
        moved[0]["updated_at"] = "2026-07-30T00:00:00Z"
        with mock.patch(
            "scripts.processor.frozen_replay.FROZEN_SNAPSHOT_SHA256",
            snapshot,
        ):
            with self.assertRaises(ProcessorError):
                refetch_frozen_source(
                    ROOT,
                    receipt,
                    queue_fetcher=lambda _root: moved,
                )
            missing = queue[1:]
            with self.assertRaises(ProcessorError):
                refetch_frozen_source(
                    ROOT,
                    receipt,
                    queue_fetcher=lambda _root: missing,
                )

    def test_body_hash_mismatch_fails_closed(self):
        receipt, queue, snapshot = self.authority()
        queue[0]["body"] += "-changed"
        with mock.patch(
            "scripts.processor.frozen_replay.FROZEN_SNAPSHOT_SHA256",
            snapshot,
        ):
            with self.assertRaises(ProcessorError):
                refetch_frozen_source(
                    ROOT,
                    receipt,
                    queue_fetcher=lambda _root: queue,
                )


if __name__ == "__main__":
    unittest.main()
