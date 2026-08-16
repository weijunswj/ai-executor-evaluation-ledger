import copy
import io
import json
import os
import shutil
import subprocess
import tempfile
import tarfile
import unittest
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

from scripts.processor.batch_processor import (
    ProcessBatchConfig,
    build_batch_candidate,
    candidate_commit_authority_message,
)
from scripts.processor.common import (
    FROZEN_BATCH_ID,
    ProcessorError,
    canonical_json_line_bytes,
    git_tree_file_bindings,
    git_tree_manifest_sha256,
    sha256_bytes,
)
from scripts.processor.frozen_replay import FrozenReplayResult
from scripts import seal_batch_receipt
from scripts.seal_batch_receipt import build_sealed_receipt
from scripts import validate_receipts as receipt_validator
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    _load_schema,
    _parse_batch,
    validate_all_tracked_batch_receipts,
    validate_batch_receipt_object,
)

ROOT = Path(__file__).resolve().parents[1]
# Durable receipt-only seal whose parent is the matching frozen candidate.
FROZEN_RECEIPT_SEAL = "d54fb99da162f49ccb616a8756725b9aea83ac1d"
FROZEN_RECEIPT_PATH = (
    "ledger/receipts/batches/batch-20260729-gate3-amendment-004.json"
)
FROZEN_EVALUATION_COUNT = 59
FROZEN_EVALUATIONS_SHA256 = "387dfc1347189555ef91eabf767e62738f777b2e80b79f5378e95170df40cb64"


class TestReceiptValidation(unittest.TestCase):
    def _current_and_terminal_shas(self):
        terminal_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        parent_sha = subprocess.run(
            ["git", "rev-parse", "HEAD^"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        terminal_receipt = json.loads(
            receipt_validator.git_object_bytes(
                ROOT,
                terminal_sha,
                FROZEN_RECEIPT_PATH,
            ).decode("utf-8")
        )
        receipt_candidate_sha = terminal_receipt["candidate_content_commit_sha"]
        if receipt_candidate_sha == parent_sha:
            return receipt_candidate_sha, terminal_sha
        return terminal_sha, terminal_sha

    def _frozen_historical_receipt(self):
        return json.loads(
            receipt_validator.git_object_bytes(
                ROOT,
                FROZEN_RECEIPT_SEAL,
                FROZEN_RECEIPT_PATH,
            ).decode("utf-8")
        )

    def test_frozen_draft_migrates_without_identity_or_rejection_prose(self):
        tracked = json.loads(
            (
                ROOT
                / "ledger/receipts/batches/batch-20260729-gate3-amendment-004.json"
            ).read_text(encoding="utf-8")
        )
        candidate_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        fingerprints = [
            {
                "id": binding["comment_id"],
                "created_at": binding["created_at"],
                "updated_at": binding["updated_at"],
                "body_sha256": binding["body_sha256"],
            }
            for binding in tracked["comment_bindings"]
        ]
        replayed_outcomes = copy.deepcopy(tracked["terminal_outcomes"])
        changed_id = next(
            comment_id
            for comment_id, outcome in replayed_outcomes.items()
            if outcome["outcome_code"] not in {"admitted", "already_recorded"}
        )
        replacement_code = (
            "authority_missing"
            if replayed_outcomes[changed_id]["outcome_code"] == "no_marker"
            else "no_marker"
        )
        replayed_outcomes[changed_id]["outcome_code"] = replacement_code
        replayed_bindings = copy.deepcopy(tracked["comment_bindings"])
        next(
            binding
            for binding in replayed_bindings
            if str(binding["comment_id"]) == changed_id
        )["outcome_code"] = replacement_code
        replay = FrozenReplayResult(
            candidate_files={},
            artifact_hashes={},
            canonical_hashes=tracked["canonical_hashes"],
            terminal_outcomes=replayed_outcomes,
            admitted_run_ids=tuple(tracked["admitted_run_ids"]),
            accepted_record_proofs=tracked["accepted_record_proofs"],
            canonical_record_hashes=tracked["canonical_record_hashes"],
            comment_bindings=tuple(replayed_bindings),
            source_comment_ids=tuple(tracked["source_comment_ids"]),
            source_body_sha256=tracked["source_body_sha256"],
            source_snapshot_sha256=tracked["queue_snapshot_sha256"],
            later_comment_count=0,
        )
        with mock.patch(
            "scripts.seal_batch_receipt.replay_frozen_from_receipt",
            return_value=replay,
        ):
            receipt = build_sealed_receipt(
                ROOT,
                candidate_content_commit_sha=candidate_sha,
                source_reader=lambda _root, _source: {
                    "comments": [{} for _item in fingerprints],
                    "fingerprints": fingerprints,
                },
            )
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["full_queue_count"], 101)
        self.assertEqual(receipt["selected_comment_count"], 101)
        self.assertEqual(receipt["terminal_outcome_count"], 101)
        self.assertEqual(
            len(receipt["admitted_run_ids"]),
            len(replay.admitted_run_ids),
        )
        self.assertEqual(
            receipt["terminal_outcomes"][changed_id]["outcome_code"],
            replacement_code,
        )
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

    def test_frozen_current_append_candidate_seals_against_full_current_hashes(self):
        candidate_sha, terminal_sha = self._current_and_terminal_shas()
        historical_receipt = self._frozen_historical_receipt()
        historical_candidate_sha = historical_receipt["candidate_content_commit_sha"]
        self.assertEqual(historical_receipt["full_queue_count"], 101)
        self.assertEqual(historical_receipt["selected_comment_count"], 101)
        self.assertEqual(historical_receipt["terminal_outcome_count"], 101)
        self.assertEqual(historical_receipt["admitted_run_ids"], [])
        fingerprints = [
            {
                "id": binding["comment_id"],
                "created_at": binding["created_at"],
                "updated_at": binding["updated_at"],
                "body_sha256": binding["body_sha256"],
            }
            for binding in historical_receipt["comment_bindings"]
        ]
        replay = FrozenReplayResult(
            candidate_files={
                relative_path: receipt_validator.git_object_bytes(
                    ROOT,
                    historical_candidate_sha,
                    relative_path,
                )
                for relative_path in (
                    "evaluations.jsonl",
                    "ledger/dispositions.jsonl",
                )
            },
            artifact_hashes={},
            canonical_hashes=historical_receipt["canonical_hashes"],
            terminal_outcomes=historical_receipt["terminal_outcomes"],
            admitted_run_ids=tuple(historical_receipt["admitted_run_ids"]),
            accepted_record_proofs=historical_receipt["accepted_record_proofs"],
            canonical_record_hashes=historical_receipt["canonical_record_hashes"],
            comment_bindings=tuple(historical_receipt["comment_bindings"]),
            source_comment_ids=tuple(historical_receipt["source_comment_ids"]),
            source_body_sha256=historical_receipt["source_body_sha256"],
            source_snapshot_sha256=historical_receipt["queue_snapshot_sha256"],
            later_comment_count=0,
        )
        live = {
            "comments": [{} for _item in fingerprints],
            "fingerprints": fingerprints,
        }
        with mock.patch(
            "scripts.seal_batch_receipt.replay_frozen_from_receipt",
            return_value=replay,
        ):
            sealed = build_sealed_receipt(
                ROOT,
                candidate_content_commit_sha=candidate_sha,
                source_reader=lambda _root, _source: live,
            )

        frozen_evaluations = receipt_validator.git_object_bytes(
            ROOT,
            historical_candidate_sha,
            "evaluations.jsonl",
        )
        current_evaluations = receipt_validator.git_object_bytes(
            ROOT,
            candidate_sha,
            "evaluations.jsonl",
        )
        terminal_evaluations = receipt_validator.git_object_bytes(
            ROOT,
            terminal_sha,
            "evaluations.jsonl",
        )
        frozen_records = frozen_evaluations.splitlines()
        current_records = current_evaluations.splitlines()
        later_records = [
            json.loads(line.decode("utf-8"))
            for line in current_records[len(frozen_records) :]
        ]
        self.assertEqual(len(frozen_records), FROZEN_EVALUATION_COUNT)
        self.assertEqual(sha256_bytes(frozen_evaluations), FROZEN_EVALUATIONS_SHA256)
        self.assertEqual(
            frozen_evaluations,
            replay.candidate_files["evaluations.jsonl"],
        )
        self.assertTrue(current_evaluations.startswith(frozen_evaluations))
        self.assertEqual(current_records[: len(frozen_records)], frozen_records)
        self.assertTrue(later_records)
        self.assertTrue(
            all(record.get("record_type") == "evaluation" for record in later_records)
        )
        frozen_run_ids = {
            json.loads(line.decode("utf-8"))["run_id"] for line in frozen_records
        }
        self.assertTrue(
            frozen_run_ids.isdisjoint(record["run_id"] for record in later_records)
        )
        current_record_count = len(current_records)
        frozen_record_count = len(frozen_records)
        terminal_record_count = len(terminal_evaluations.splitlines())
        self.assertGreater(current_record_count, frozen_record_count)
        self.assertEqual(current_evaluations, terminal_evaluations)
        self.assertEqual(current_record_count, terminal_record_count)
        self.assertEqual(sealed["candidate_content_commit_sha"], candidate_sha)
        for hash_name, relative_path in CANONICAL_PATHS.items():
            current_bytes = receipt_validator.git_object_bytes(
                ROOT,
                candidate_sha,
                relative_path,
            )
            terminal_bytes = receipt_validator.git_object_bytes(
                ROOT,
                terminal_sha,
                relative_path,
            )
            self.assertEqual(current_bytes, terminal_bytes, hash_name)
            self.assertEqual(
                sealed["canonical_hashes"][hash_name],
                sha256_bytes(current_bytes),
                hash_name,
            )
        if terminal_sha != candidate_sha:
            terminal_receipt = json.loads(
                receipt_validator.git_object_bytes(
                    ROOT,
                    terminal_sha,
                    FROZEN_RECEIPT_PATH,
                ).decode("utf-8")
            )
            self.assertEqual(
                terminal_receipt["candidate_content_commit_sha"],
                candidate_sha,
            )
        self.assertNotEqual(
            sealed["canonical_hashes"]["evaluations_jsonl"],
            historical_receipt["canonical_hashes"]["evaluations_jsonl"],
        )
        for hash_name in (
            "readme_md",
            "scorecard_md",
            "model_recommendation_json",
        ):
            self.assertNotEqual(
                sealed["canonical_hashes"][hash_name],
                historical_receipt["canonical_hashes"][hash_name],
            )

        validate_batch_receipt_object(
            ROOT,
            sealed,
            authority_sha=candidate_sha,
        )
        with mock.patch.object(
            receipt_validator,
            "refetch_frozen_source",
            return_value=live,
        ), mock.patch.object(
            receipt_validator,
            "replay_frozen_from_receipt",
            return_value=replay,
        ):
            evidence = receipt_validator._validate_frozen_source_replay(
                ROOT,
                receipt=sealed,
                candidate_sha=candidate_sha,
                seal_sha=terminal_sha,
            )
        self.assertEqual(evidence["outcomes"], 101)
        self.assertEqual(evidence["admissions"], 0)

        historical_hash_receipt = copy.deepcopy(sealed)
        historical_hash_receipt["canonical_hashes"] = dict(
            historical_receipt["canonical_hashes"]
        )
        with self.assertRaises(ReceiptValidationError):
            validate_batch_receipt_object(
                ROOT,
                historical_hash_receipt,
                authority_sha=candidate_sha,
            )

        wrong_candidate_commit = copy.deepcopy(sealed)
        wrong_candidate_commit["candidate_content_commit_sha"] = historical_candidate_sha
        with self.assertRaises(ReceiptValidationError):
            validate_batch_receipt_object(
                ROOT,
                wrong_candidate_commit,
                authority_sha=candidate_sha,
            )

        changed_body_hashes = dict(replay.source_body_sha256)
        changed_body_hashes[next(iter(changed_body_hashes))] = "0" * 64
        changed_outcomes = copy.deepcopy(dict(replay.terminal_outcomes))
        changed_outcome_id = next(iter(changed_outcomes))
        changed_outcomes[changed_outcome_id] = dict(
            changed_outcomes[changed_outcome_id]
        )
        old_code = changed_outcomes[changed_outcome_id]["outcome_code"]
        changed_outcomes[changed_outcome_id]["outcome_code"] = (
            "no_marker" if old_code != "no_marker" else "authority_missing"
        )
        changed_source_ids = list(replay.source_comment_ids)
        changed_source_ids[0] += 1
        replay_variants = {
            "source fingerprint": replace(
                replay,
                source_body_sha256=changed_body_hashes,
            ),
            "outcome authority": replace(
                replay,
                terminal_outcomes=changed_outcomes,
            ),
            "source membership": replace(
                replay,
                source_comment_ids=tuple(changed_source_ids),
            ),
        }
        for label, replay_variant in replay_variants.items():
            with self.subTest(label=label):
                with mock.patch.object(
                    receipt_validator,
                    "refetch_frozen_source",
                    return_value=live,
                ), mock.patch.object(
                    receipt_validator,
                    "replay_frozen_from_receipt",
                    return_value=replay_variant,
                ):
                    with self.assertRaises(ReceiptValidationError):
                        receipt_validator._validate_frozen_source_replay(
                            ROOT,
                            receipt=sealed,
                            candidate_sha=candidate_sha,
                            seal_sha=terminal_sha,
                        )

    def test_frozen_replay_prefix_variants_fail_closed(self):
        candidate_sha, _terminal_sha = self._current_and_terminal_shas()
        historical_receipt = self._frozen_historical_receipt()
        frozen = receipt_validator.git_object_bytes(
            ROOT,
            historical_receipt["candidate_content_commit_sha"],
            "evaluations.jsonl",
        )
        current = receipt_validator.git_object_bytes(
            ROOT,
            candidate_sha,
            "evaluations.jsonl",
        )
        self.assertTrue(current.startswith(frozen))
        lines = frozen.splitlines(keepends=True)
        variants = {
            "shorter": frozen[:-1],
            "prefix mutation": bytes([frozen[0] ^ 1]) + frozen[1:],
            "record deletion": b"".join(lines[1:]) + current[len(frozen):],
            "record reorder": lines[1] + lines[0] + b"".join(lines[2:]) + current[len(frozen):],
            "prefix insertion": lines[0] + b"{}\n" + b"".join(lines[1:]) + current[len(frozen):],
            "prefix replacement": lines[0].replace(b'"run_id"', b'"run-id"', 1) + b"".join(lines[1:]) + current[len(frozen):],
            "malformed non-prefix": b"not-a-prefix\n" + current,
        }
        replay = SimpleNamespace(candidate_files={"evaluations.jsonl": frozen})
        for label, candidate in variants.items():
            with self.subTest(label=label):
                with mock.patch.object(
                    seal_batch_receipt,
                    "git_object_bytes",
                    return_value=candidate,
                ):
                    with self.assertRaises(ReceiptValidationError):
                        seal_batch_receipt._verify_frozen_replay_artifacts(
                            ROOT,
                            candidate_sha,
                            replay,
                        )

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
            "source_replay": {"adapter": "github-intake-v1"},
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
        receipt_relative = receipt_path.relative_to(root).as_posix()
        receipt["candidate_content_manifest"] = receipt_validator.git_tree_file_bindings(
            root,
            content_sha,
            excluded_paths=(receipt_relative,),
        )
        receipt["candidate_content_manifest_sha256"] = (
            receipt_validator.git_tree_manifest_sha256(
                receipt["candidate_content_manifest"]
            )
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(
            (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
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

    def test_canonical_main_accepts_receipt_only_seal_over_exact_candidate_tree(self):
        with tempfile.TemporaryDirectory(prefix="receipt-squash-test-") as raw:
            root = Path(raw)
            receipt, content_sha, _final_sha = self.fixture(root)
            tree_sha = subprocess.run(
                ["git", "rev-parse", f"{content_sha}^{{tree}}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            candidate_sha = subprocess.run(
                [
                    "git",
                    "commit-tree",
                    tree_sha,
                    "-p",
                    content_sha,
                    "-m",
                    "candidate content",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            receipt["candidate_content_commit_sha"] = candidate_sha
            receipt_path = Path(
                "ledger/receipts/batches/batch-receipt-fixture.json"
            )
            subprocess.run(
                ["git", "checkout", "-q", content_sha],
                cwd=root,
                check=True,
            )
            target = root / receipt_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(
                    "utf-8"
                )
            )
            subprocess.run(
                ["git", "add", receipt_path.as_posix()],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "receipt-only squash seal"],
                cwd=root,
                check=True,
            )
            seal_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=seal_sha,
                mode="canonical-main",
                canonical_base_sha=content_sha,
            )
            self.assertEqual(result["receipt_count"], 1)

    def test_canonical_main_uses_manifest_when_candidate_commit_is_unreachable(self):
        with tempfile.TemporaryDirectory(prefix="receipt-unreachable-candidate-") as raw:
            root = Path(raw)
            receipt, content_sha, _final_sha = self.fixture(root)
            receipt["candidate_content_commit_sha"] = "a" * 40
            receipt_path = Path(
                "ledger/receipts/batches/batch-receipt-fixture.json"
            )
            subprocess.run(
                ["git", "checkout", "-q", content_sha],
                cwd=root,
                check=True,
            )
            target = root / receipt_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(
                    "utf-8"
                )
            )
            subprocess.run(
                ["git", "add", receipt_path.as_posix()],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "receipt-only seal"],
                cwd=root,
                check=True,
            )
            seal_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=seal_sha,
                mode="canonical-main",
                canonical_base_sha=content_sha,
            )
            self.assertEqual(result["receipt_count"], 1)

    def test_generic_replay_fetches_complete_universe_and_counts_later_comments(self):
        with tempfile.TemporaryDirectory(prefix="receipt-replay-universe-") as raw:
            root = Path(raw)
            _receipt, candidate_sha, seal_sha = self.fixture(root)
            receipt_path = "ledger/receipts/batches/batch-receipt-fixture.json"
            issue_url = receipt_validator.ISSUE_142_API_URL
            comment = {
                "id": 1,
                "body": "source",
                "author_association": "OWNER",
                "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
                "created_at": "2026-07-29T10:00:00Z",
                "updated_at": "2026-07-29T10:00:00Z",
                "issue_url": issue_url,
            }
            later = {
                **comment,
                "id": 2,
                "body": "later",
                "created_at": "2026-07-29T11:00:00Z",
                "updated_at": "2026-07-29T11:00:00Z",
            }
            candidate_files = {
                relative_path: receipt_validator.git_object_bytes(
                    root, seal_sha, relative_path
                )
                for relative_path in (*CANONICAL_PATHS.values(), receipt_path)
            }
            with mock.patch.object(
                receipt_validator,
                "fetch_live_142_comments",
                create=True,
                return_value=[comment, later],
            ), mock.patch.object(
                receipt_validator,
                "build_batch_candidate",
                return_value=(
                    candidate_files,
                    {"terminal_count": 1, "admitted_count": 1},
                ),
            ):
                evidence = receipt_validator._validate_github_intake_source_replay(
                    root,
                    authority_sha=seal_sha,
                    receipt_path=receipt_path,
                    receipt=json.loads(
                        receipt_validator.git_object_bytes(
                            root, seal_sha, receipt_path
                        ).decode("utf-8")
                    ),
                    candidate_sha=candidate_sha,
                    seal_sha=seal_sha,
                )
            self.assertEqual(evidence["later_comments"], 1)

    def test_non_frozen_replay_uses_receipt_watermark_without_mocking_processor(self):
        with tempfile.TemporaryDirectory(prefix="receipt-real-replay-a132-") as raw:
            root = Path(raw)
            archive = subprocess.run(
                ["git", "archive", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
                for member in tree.getmembers():
                    tree.extract(member, root)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.name", "ledger-fixture"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "fixture" + chr(64) + "example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            comments = [
                {
                    "id": 9001,
                    "body": "ordinary retained 9001",
                    "author_association": "OWNER",
                    "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
                    "created_at": "2026-07-29T10:01:00Z",
                    "updated_at": "2026-07-29T10:01:00Z",
                },
                {
                    "id": 9002,
                    "body": "ordinary retained 9002",
                    "author_association": "OWNER",
                    "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
                    "created_at": "2026-07-29T10:02:00Z",
                    "updated_at": "2026-07-29T10:02:00Z",
                },
                {
                    "id": 9003,
                    "body": "later retained 9003",
                    "author_association": "OWNER",
                    "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
                    "created_at": "2026-07-29T10:03:00Z",
                    "updated_at": "2026-07-29T10:03:00Z",
                },
            ]
            by_id = {item["id"]: item for item in comments}
            config = ProcessBatchConfig(
                operating_mode="initial",
                base_sha=base_sha,
                canonical_main_sha=base_sha,
                batch_id="batch-real-replay-a132",
                controller_run_id="controller-real-replay-a132",
                pr_number=181,
                expected_head_sha=base_sha,
                activation_mode="dry-run",
                dry_run=True,
                source_issue_number=142,
                receipt_issue_number=143,
                repository_root=root,
                source_comment_watermark=9002,
            )
            queue = lambda _root: copy.deepcopy(comments)
            comment_fetcher = lambda comment_id, _root: copy.deepcopy(by_id[comment_id])
            owner = {"i" + "d": 7001, "l" + "ogin": "fixture-author"}
            candidate_files, dry_evidence = build_batch_candidate(
                config,
                comments=comments,
                queue_fetcher=queue,
                comment_fetcher=comment_fetcher,
                canonical_main_fetcher=lambda _root: base_sha,
                owner_fetcher=lambda _root: owner,
            )

            with tempfile.TemporaryDirectory(prefix="receipt-real-replay-index-") as index_raw:
                git_env = os.environ.copy()
                git_env["GIT_INDEX_FILE"] = str(Path(index_raw) / "index")
                git_env["GIT_AUTHOR_NAME"] = "ledger-fixture"
                git_env["GIT_AUTHOR_EMAIL"] = "fixture" + chr(64) + "example.invalid"
                git_env["GIT_COMMITTER_NAME"] = "ledger-fixture"
                git_env["GIT_COMMITTER_EMAIL"] = "fixture" + chr(64) + "example.invalid"
                subprocess.run(
                    ["git", "read-tree", base_sha],
                    cwd=root,
                    env=git_env,
                    check=True,
                )
                for relative_path in (
                    "evaluations.jsonl",
                    "ledger/dispositions.jsonl",
                    "README.md",
                    "scorecard.md",
                    "analysis/model-recommendation.json",
                ):
                    blob_sha = subprocess.run(
                        ["git", "hash-object", "-w", "--stdin"],
                        cwd=root,
                        env=git_env,
                        input=candidate_files[relative_path],
                        capture_output=True,
                        check=True,
                    ).stdout.decode("ascii").strip()
                    subprocess.run(
                        [
                            "git",
                            "update-index",
                            "--add",
                            "--cacheinfo",
                            "100644",
                            blob_sha,
                            relative_path,
                        ],
                        cwd=root,
                        env=git_env,
                        check=True,
                    )
                tree_sha = subprocess.run(
                    ["git", "write-tree"],
                    cwd=root,
                    env=git_env,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                candidate_sha = subprocess.run(
                    [
                        "git",
                        "commit-tree",
                        tree_sha,
                        "-p",
                        base_sha,
                        "-m",
                        candidate_commit_authority_message(
                            config,
                            dry_evidence["snapshot_hash"],
                        ),
                    ],
                    cwd=root,
                    env=git_env,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()

            sealed_config = ProcessBatchConfig(**{
                **config.__dict__,
                "candidate_content_commit_sha": candidate_sha,
            })
            sealed_files, sealed_evidence = build_batch_candidate(
                sealed_config,
                comments=comments,
                queue_fetcher=queue,
                comment_fetcher=comment_fetcher,
                canonical_main_fetcher=lambda _root: base_sha,
                owner_fetcher=lambda _root: owner,
            )
            receipt_path = "ledger/receipts/batches/batch-real-replay-a132.json"
            receipt = json.loads(sealed_files[receipt_path].decode("utf-8"))

            with tempfile.TemporaryDirectory(prefix="receipt-real-replay-seal-") as index_raw:
                git_env = os.environ.copy()
                git_env["GIT_INDEX_FILE"] = str(Path(index_raw) / "index")
                git_env["GIT_AUTHOR_NAME"] = "ledger-fixture"
                git_env["GIT_AUTHOR_EMAIL"] = "fixture" + chr(64) + "example.invalid"
                git_env["GIT_COMMITTER_NAME"] = "ledger-fixture"
                git_env["GIT_COMMITTER_EMAIL"] = "fixture" + chr(64) + "example.invalid"
                subprocess.run(
                    ["git", "read-tree", candidate_sha],
                    cwd=root,
                    env=git_env,
                    check=True,
                )
                receipt_blob = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=root,
                    env=git_env,
                    input=sealed_files[receipt_path],
                    capture_output=True,
                    check=True,
                ).stdout.decode("ascii").strip()
                subprocess.run(
                    [
                        "git",
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        "100644",
                        receipt_blob,
                        receipt_path,
                    ],
                    cwd=root,
                    env=git_env,
                    check=True,
                )
                seal_tree = subprocess.run(
                    ["git", "write-tree"],
                    cwd=root,
                    env=git_env,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                seal_sha = subprocess.run(
                    [
                        "git",
                        "commit-tree",
                        seal_tree,
                        "-p",
                        candidate_sha,
                        "-m",
                        "receipt seal",
                    ],
                    cwd=root,
                    env=git_env,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            subprocess.run(["git", "checkout", "-q", seal_sha], cwd=root, check=True)

            self.assertEqual(dry_evidence["source_comment_watermark"], 9002)
            self.assertTrue(sealed_evidence["receipt_sealed"])
            self.assertEqual(receipt["source_comment_ids"], [9001, 9002])
            self.assertNotIn("9003", receipt["terminal_outcomes"])
            with mock.patch.object(
                receipt_validator,
                "fetch_live_142_comments",
                return_value=comments,
            ):
                replay_evidence = receipt_validator._validate_github_intake_source_replay(
                    root,
                    authority_sha=seal_sha,
                    receipt_path=receipt_path,
                    receipt=receipt,
                    candidate_sha=candidate_sha,
                    seal_sha=seal_sha,
                )
            self.assertEqual(replay_evidence["outcomes"], 2)
            self.assertEqual(replay_evidence["admissions"], 0)
            self.assertEqual(replay_evidence["later_comments"], 1)

            changed = copy.deepcopy(receipt)
            changed["source_comment_watermark"] = 9003
            missing = copy.deepcopy(receipt)
            del missing["source_comment_watermark"]
            with mock.patch.object(
                receipt_validator,
                "fetch_live_142_comments",
                return_value=comments,
            ):
                for invalid_receipt in (changed, missing):
                    with self.subTest(invalid_receipt=invalid_receipt is missing):
                        with self.assertRaises(ReceiptValidationError):
                            receipt_validator._validate_github_intake_source_replay(
                                root,
                                authority_sha=seal_sha,
                                receipt_path=receipt_path,
                                receipt=invalid_receipt,
                                candidate_sha=candidate_sha,
                                seal_sha=seal_sha,
                            )

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


    def test_canonical_main_rejects_malformed_receipt_after_receipt_delta(self):
        with tempfile.TemporaryDirectory(prefix="receipt-canonical-invalid-") as raw:
            root = Path(raw)
            _receipt, content_sha, _final_sha = self.fixture(root)
            subprocess.run(
                ["git", "checkout", "-q", content_sha],
                cwd=root,
                check=True,
            )
            receipt_path = root / FROZEN_RECEIPT_PATH
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(b'{"schema_version":2}\n')
            subprocess.run(
                ["git", "add", FROZEN_RECEIPT_PATH],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "malformed receipt delta"],
                cwd=root,
                check=True,
            )
            seal_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(
                    root,
                    authority_sha=seal_sha,
                    mode="canonical-main",
                    canonical_base_sha=content_sha,
                )

class TestA13ReceiptConvergence(unittest.TestCase):
    current_receipt_path = (
        "ledger/receipts/batches/batch-a13-current.json"
    )

    def _git_sha(self, root):
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def _git_output(self, root, *args):
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def _commit_json(self, root, relative_path, value, message):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            (
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            ).encode("utf-8")
        )
        subprocess.run(["git", "add", relative_path], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
        return self._git_sha(root)

    def _build_later_topology(self, root):
        fixture = TestReceiptValidation()
        receipt, content_sha, unrelated_seal = fixture.fixture(root)
        subprocess.run(["git", "checkout", "-q", content_sha], cwd=root, check=True)

        historical = copy.deepcopy(receipt)
        historical["batch_id"] = FROZEN_BATCH_ID
        historical.pop("source_replay", None)
        historical["candidate_content_commit_sha"] = content_sha
        historical["candidate_content_manifest"] = git_tree_file_bindings(
            root,
            content_sha,
            excluded_paths=(FROZEN_RECEIPT_PATH,),
        )
        historical["candidate_content_manifest_sha256"] = (
            git_tree_manifest_sha256(historical["candidate_content_manifest"])
        )
        historical_seal = self._commit_json(
            root,
            FROZEN_RECEIPT_PATH,
            historical,
            "historical frozen receipt",
        )

        (root / "a13-marker.txt").write_text("later candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "a13-marker.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "later candidate"], cwd=root, check=True)
        candidate_sha = self._git_sha(root)

        current = copy.deepcopy(receipt)
        current["batch_id"] = "batch-a13-current"
        current["batch_mode"] = "incremental"
        current["base_sha"] = historical_seal
        current["canonical_main_sha"] = historical_seal
        current["candidate_content_commit_sha"] = candidate_sha
        current["candidate_content_manifest"] = git_tree_file_bindings(
            root,
            candidate_sha,
            excluded_paths=(self.current_receipt_path,),
        )
        current["candidate_content_manifest_sha256"] = git_tree_manifest_sha256(
            current["candidate_content_manifest"]
        )
        current["canonical_hashes"] = {
            name: sha256_bytes(
                receipt_validator.git_object_bytes(root, candidate_sha, relative)
            )
            for name, relative in CANONICAL_PATHS.items()
        }
        current_pr_seal = self._commit_json(
            root,
            self.current_receipt_path,
            current,
            "raw PR receipt-only seal",
        )
        canonical_seal = self._git_output(
            root,
            "commit-tree",
            self._git_output(root, "rev-parse", f"{current_pr_seal}^{{tree}}"),
            "-p",
            historical_seal,
            "-m",
            "canonical squash-style seal",
        )
        subprocess.run(["git", "checkout", "-q", canonical_seal], cwd=root, check=True)
        (root / "a13-later-code-only.txt").write_text(
            "later code-only\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "a13-later-code-only.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "later code-only descendant"], cwd=root, check=True)
        later_code_sha = self._git_sha(root)
        return {
            "historical": historical,
            "historical_seal": historical_seal,
            "base_sha": historical_seal,
            "candidate_sha": candidate_sha,
            "current_pr_seal": current_pr_seal,
            "current_seal": canonical_seal,
            "later_code_sha": later_code_sha,
            "unrelated_seal": unrelated_seal,
            "root": root,
        }

    def test_current_frozen_receipt_uses_strict_canonical_base(self):
        with tempfile.TemporaryDirectory(prefix="a13-current-frozen-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=topology["historical_seal"],
                mode="canonical-main",
                canonical_base_sha=topology["historical"]["base_sha"],
            )
            self.assertEqual(
                result["receipt_seals"][FROZEN_RECEIPT_PATH],
                topology["historical_seal"],
            )
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(
                    root,
                    authority_sha=topology["historical_seal"],
                    mode="canonical-main",
                    canonical_base_sha=topology["candidate_sha"],
                )

    def test_later_receipt_push_preserves_historical_seal_and_validates_current_base(self):
        with tempfile.TemporaryDirectory(prefix="a13-later-receipt-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=topology["current_seal"],
                mode="canonical-main",
                canonical_base_sha=topology["base_sha"],
            )
            self.assertEqual(
                result["receipt_seals"][FROZEN_RECEIPT_PATH],
                topology["historical_seal"],
            )
            self.assertEqual(
                result["receipt_seals"][self.current_receipt_path],
                topology["current_seal"],
            )
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(
                    root,
                    authority_sha=topology["current_seal"],
                    mode="canonical-main",
                    canonical_base_sha=topology["candidate_sha"],
                )

    def test_later_receipt_push_rejects_historical_mutation_and_manifest_corruption(self):
        for label, mutate in (
            (
                "historical bytes",
                lambda receipt: receipt.update(
                    controller_run_id="controller-mutated"
                ),
            ),
            (
                "historical manifest",
                lambda receipt: receipt["candidate_content_manifest"][0].update(
                    path="../unsafe"
                ),
            ),
        ):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(prefix="a13-history-corrupt-") as raw:
                    root = Path(raw)
                    topology = self._build_later_topology(root)
                    mutated = copy.deepcopy(topology["historical"])
                    mutate(mutated)
                    authority = self._commit_json(
                        root,
                        FROZEN_RECEIPT_PATH,
                        mutated,
                        "corrupt historical receipt",
                    )
                    with self.assertRaises(ReceiptValidationError):
                        validate_all_tracked_batch_receipts(
                            root,
                            authority_sha=authority,
                            mode="canonical-main",
                            canonical_base_sha=topology["current_seal"],
                        )

    def test_later_receipt_push_rejects_historical_seal_without_ancestry(self):
        with tempfile.TemporaryDirectory(prefix="a13-history-ancestry-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)

            def seal_for_path(_root, **kwargs):
                if kwargs["receipt_path"] == FROZEN_RECEIPT_PATH:
                    return topology["unrelated_seal"]
                return topology["current_seal"]

            with mock.patch.object(
                receipt_validator,
                "_terminal_seal_commit",
                side_effect=seal_for_path,
            ):
                with self.assertRaises(ReceiptValidationError):
                    validate_all_tracked_batch_receipts(
                        root,
                        authority_sha=topology["current_seal"],
                        mode="canonical-main",
                        canonical_base_sha=topology["base_sha"],
                    )


    def test_incremental_squash_seal_validates_at_later_code_only_descendant(self):
        with tempfile.TemporaryDirectory(prefix="a13-incremental-squash-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=topology["later_code_sha"],
                mode="canonical-main",
            )
            self.assertEqual(
                result["receipt_seals"][FROZEN_RECEIPT_PATH],
                topology["historical_seal"],
            )
            self.assertEqual(
                result["receipt_seals"][self.current_receipt_path],
                topology["current_seal"],
            )
            self.assertEqual(topology["base_sha"], topology["historical_seal"])

    def test_incremental_raw_pr_seal_keeps_candidate_parent_semantics(self):
        with tempfile.TemporaryDirectory(prefix="a13-incremental-pr-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            result = validate_all_tracked_batch_receipts(
                root,
                authority_sha=topology["current_pr_seal"],
                mode="pr",
            )
            self.assertEqual(
                result["changed_receipt_path"],
                self.current_receipt_path,
            )
            self.assertEqual(result["final_parent_sha"], topology["candidate_sha"])

    def test_incremental_recorded_authority_must_resolve_and_match(self):
        with tempfile.TemporaryDirectory(prefix="a13-incremental-authority-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            current = json.loads(
                subprocess.run(
                    [
                        "git",
                        "show",
                        f'{topology["current_pr_seal"]}:{self.current_receipt_path}',
                    ],
                    cwd=root,
                    capture_output=True,
                    check=True,
                ).stdout
            )
            for field in ("base_sha", "canonical_main_sha"):
                broken = copy.deepcopy(current)
                broken[field] = "a" * 40
                with self.subTest(field=field), self.assertRaises(ReceiptValidationError):
                    receipt_validator._resolve_incremental_canonical_authority(
                        root,
                        broken,
                    )
            mismatched = copy.deepcopy(current)
            mismatched["canonical_main_sha"] = topology["candidate_sha"]
            with self.assertRaises(ReceiptValidationError):
                receipt_validator._resolve_incremental_canonical_authority(
                    root,
                    mismatched,
                )

    def test_incremental_canonical_seal_parent_and_candidate_bindings_remain_strict(self):
        with tempfile.TemporaryDirectory(prefix="a13-incremental-strict-") as raw:
            root = Path(raw)
            topology = self._build_later_topology(root)
            wrong_seal = self._git_output(
                root,
                "commit-tree",
                self._git_output(
                    root,
                    "rev-parse",
                    f'{topology["current_pr_seal"]}^{{tree}}',
                ),
                "-p",
                topology["candidate_sha"],
                "-m",
                "wrong canonical parent",
            )
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(
                    root,
                    authority_sha=wrong_seal,
                    mode="canonical-main",
                )

            current = json.loads(
                subprocess.run(
                    [
                        "git",
                        "show",
                        f'{topology["current_pr_seal"]}:{self.current_receipt_path}',
                    ],
                    cwd=root,
                    capture_output=True,
                    check=True,
                ).stdout
            )
            broken_manifest = copy.deepcopy(current)
            broken_manifest["candidate_content_manifest"][0]["content_sha256"] = "0" * 64
            with self.assertRaises(ReceiptValidationError):
                receipt_validator._validate_candidate_manifest(
                    root,
                    receipt=broken_manifest,
                    receipt_path=self.current_receipt_path,
                    candidate_sha=topology["candidate_sha"],
                    seal_sha=topology["current_seal"],
                )

            wrong_candidate = copy.deepcopy(current)
            wrong_candidate["candidate_content_commit_sha"] = topology["base_sha"]
            with self.assertRaises(ReceiptValidationError):
                validate_batch_receipt_object(
                    root,
                    wrong_candidate,
                    authority_sha=topology["current_seal"],
                )


class TestA13ManifestPathContract(unittest.TestCase):
    current_receipt_path = (
        "ledger/receipts/batches/batch-a13-current.json"
    )

    def _fake_tree_run(self, listing):
        def run(args, **_kwargs):
            if args[1] == "ls-tree":
                return SimpleNamespace(returncode=0, stdout=listing)
            if args[1] == "cat-file":
                return SimpleNamespace(returncode=0, stdout=b"payload")
            raise AssertionError(args)

        return run

    def _blob_entry(self, path, *, object_sha="a" * 40):
        raw_path = path if isinstance(path, bytes) else path.encode("utf-8")
        return b"100644 blob " + object_sha.encode("ascii") + b"\t" + raw_path + b"\0"

    def test_normal_tree_is_complete_deterministic_and_excludes_only_authorized_receipt(self):
        receipt_path = FROZEN_RECEIPT_PATH.encode("utf-8")
        listing = (
            self._blob_entry("z.txt")
            + self._blob_entry("a.txt", object_sha="b" * 40)
            + self._blob_entry(receipt_path, object_sha="c" * 40)
        )
        with mock.patch(
            "scripts.processor.common.subprocess.run",
            side_effect=self._fake_tree_run(listing),
        ):
            first = git_tree_file_bindings(
                Path("."),
                "a" * 40,
                excluded_paths=(FROZEN_RECEIPT_PATH,),
            )
            second = git_tree_file_bindings(
                Path("."),
                "a" * 40,
                excluded_paths=(FROZEN_RECEIPT_PATH,),
            )
        self.assertEqual(first, second)
        self.assertEqual([item["path"] for item in first], ["a.txt", "z.txt"])

    def test_every_other_unsafe_tracked_path_fails_closed(self):
        cases = {
            "backslash": b"unsafe\\name",
            "absolute": b"/absolute",
            "windows_absolute": b"C:/absolute",
            "traversal": b"../traversal",
            "dot_traversal": b"dir/../traversal",
            "empty": b"",
            "invalid_utf8": b"\xff",
        }
        for label, raw_path in cases.items():
            with self.subTest(label=label):
                listing = self._blob_entry(raw_path)
                with mock.patch(
                    "scripts.processor.common.subprocess.run",
                    side_effect=self._fake_tree_run(listing),
                ):
                    with self.assertRaises(ProcessorError):
                        git_tree_file_bindings(Path("."), "a" * 40)

        non_blob = (
            b"040000 tree "
            + (b"d" * 40)
            + b"\tdirectory\0"
        )
        with mock.patch(
            "scripts.processor.common.subprocess.run",
            side_effect=self._fake_tree_run(non_blob),
        ):
            with self.assertRaises(ProcessorError):
                git_tree_file_bindings(Path("."), "a" * 40)

    def test_validator_cannot_accept_manifest_by_omitting_unsafe_tracked_path(self):
        unsafe = self._blob_entry(b"unsafe\\name")
        receipt = {
            "batch_id": "batch-a13-current",
            "candidate_content_manifest": [],
            "candidate_content_manifest_sha256": git_tree_manifest_sha256([]),
        }
        with mock.patch(
            "scripts.processor.common.subprocess.run",
            side_effect=self._fake_tree_run(unsafe),
        ):
            with self.assertRaises(ProcessorError):
                git_tree_file_bindings(Path("."), "a" * 40)
            with self.assertRaises(ReceiptValidationError):
                receipt_validator._validate_candidate_manifest(
                    Path("."),
                    receipt=receipt,
                    receipt_path=self.current_receipt_path,
                    candidate_sha="a" * 40,
                )



class TestA14SharedTreeFraming(unittest.TestCase):
    revision = "a" * 40
    object_sha = "b" * 40

    def run_helper(self, listing: bytes):
        def runner(args, **_kwargs):
            if args[1] == "ls-tree":
                return SimpleNamespace(returncode=0, stdout=listing)
            if args[1] == "cat-file":
                return SimpleNamespace(returncode=0, stdout=b"payload")
            raise AssertionError(args)

        with mock.patch(
            "scripts.processor.common.subprocess.run",
            side_effect=runner,
        ):
            return git_tree_file_bindings(Path("."), self.revision)

    def test_empty_tree_is_valid(self):
        self.assertEqual(self.run_helper(b""), [])

    def test_incomplete_or_ambiguous_ls_tree_framing_fails_closed(self):
        entry = (
            b"100644 blob "
            + self.object_sha.encode("ascii")
            + b"\tfile.txt\0"
        )
        for listing in (entry[:-1], entry + b"\0", b"\0"):
            with self.subTest(listing=listing):
                with self.assertRaises(ProcessorError) as raised:
                    self.run_helper(listing)
                self.assertEqual(raised.exception.code, "processor_integrity_failure")

    def test_shared_metadata_and_object_tokens_are_strict(self):
        cases = (
            b"100644  blob " + self.object_sha.encode("ascii") + b"\tfile.txt\0",
            b"100644 blob " + b"c" * 39 + b"\xff" + b"\tfile.txt\0",
            b"10064x blob " + self.object_sha.encode("ascii") + b"\tfile.txt\0",
        )
        for listing in cases:
            with self.subTest(listing=listing):
                with self.assertRaises(ProcessorError):
                    self.run_helper(listing)

if __name__ == "__main__":
    unittest.main()
