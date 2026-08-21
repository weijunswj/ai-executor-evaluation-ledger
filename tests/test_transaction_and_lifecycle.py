import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

from scripts.processor import cleanup_workflow
from scripts.processor.cleanup_workflow import (
    CleanupConfig,
    CANONICAL_PATHS,
    RECEIPT_ISSUE_ENDPOINT,
    RECEIPT_VALIDATOR,
    RECORDED_COMMENT_MAX_CHARS,
    RECORDED_MARKER,
    _parse_recorded_receipt_body,
    _readback_live_authority,
    _is_commit_ancestor,
    _receipt_matches_authority,
    prepare_cleanup_receipt,
    _recorded_receipt_status,
    publish_cleanup_receipt,
    run_cleanup,
    _retained_comment_evidence,
)
from scripts.processor.common import (
    ProcessorError,
    canonical_json_bytes,
    git_tree_file_bindings,
    git_tree_manifest_sha256,
    canonical_json_line_bytes,
    safe_author_hash,
    safe_comment_body_hash,
    sha256_bytes,
)
from scripts.validate_receipts import (
    ReceiptValidationError,
    validate_batch_receipt_object,
)
from scripts.processor.transaction import (
    RepositoryPathGuard,
    recover_incomplete_transaction,
    recovery_journal_path,
    replace_tracked_files,
    snapshot_tracked_files,
)

ROOT = Path(__file__).resolve().parents[1]


class TestTransactionAndLifecycle(unittest.TestCase):
    def transaction_fixture(self, root: Path):
        paths = {
            "evaluations.jsonl": b"old-evaluations\n",
            "README.md": b"old-readme\n",
            "scorecard.md": b"old-scorecard\n",
            "ledger/receipts/batches/one.json": b"old-receipt\n",
        }
        for relative, content in paths.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture" + "@" + "example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "fixture"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
        candidate = {relative: content.replace(b"old", b"new") for relative, content in paths.items()}
        return paths, candidate

    def test_every_replacement_boundary_rolls_back_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix="ledger-tx-test-") as raw:
            root = Path(raw)
            paths, candidate = self.transaction_fixture(root)
            boundaries = [
                (stage, relative)
                for relative in paths
                for stage in ("candidate_file_write", "before_candidate_replace", "after_candidate_replace")
            ]
            boundaries.extend(("between_candidate_replacements", relative) for relative in tuple(paths)[:-1])
            boundaries.append(("candidate_verification", ""))
            for event, event_path in boundaries:
                before = {relative: (root / relative).read_bytes() for relative in paths}

                def hook(stage, relative, wanted=event, wanted_path=event_path):
                    if stage == wanted and relative == wanted_path:
                        raise RuntimeError("injected_failure")

                with self.assertRaises(RuntimeError):
                    replace_tracked_files(root, candidate, failure_hook=hook)
                self.assertEqual(
                    {relative: (root / relative).read_bytes() for relative in paths},
                    before,
                    f"{event}:{event_path}",
                )
                self.assertFalse(recovery_journal_path(root).exists(), f"{event}:{event_path}")

    def test_restoration_failures_preserve_recoverable_journal(self):
        restoration_points = (
            ("before_restore", "evaluations.jsonl"),
            ("after_restore", "evaluations.jsonl"),
            ("between_restorations", "evaluations.jsonl"),
            ("before_restore", "README.md"),
            ("after_restore", "README.md"),
            ("between_restorations", "README.md"),
            ("before_restore", "scorecard.md"),
            ("after_restore", "scorecard.md"),
            ("between_restorations", "scorecard.md"),
            ("before_restore", "ledger/receipts/batches/one.json"),
            ("after_restore", "ledger/receipts/batches/one.json"),
            ("restoration_verification", ""),
        )
        for stage_to_fail, path_to_fail in restoration_points:
            with tempfile.TemporaryDirectory(prefix="ledger-restore-test-") as raw:
                root = Path(raw)
                paths, candidate = self.transaction_fixture(root)
                original = {relative: (root / relative).read_bytes() for relative in paths}

                def hook(stage, relative):
                    if stage == "after_candidate_replace" and relative == "evaluations.jsonl":
                        raise RuntimeError("begin_restoration")
                    if stage == stage_to_fail and relative == path_to_fail:
                        raise RuntimeError("injected_restoration_failure")

                with self.assertRaises(ProcessorError) as raised:
                    replace_tracked_files(root, candidate, failure_hook=hook)
                self.assertEqual(raised.exception.code, "processor_recovery_required")
                self.assertTrue(recovery_journal_path(root).is_dir())
                self.assertTrue(recover_incomplete_transaction(root))
                self.assertEqual(
                    {relative: (root / relative).read_bytes() for relative in paths},
                    original,
                )
                self.assertFalse(recovery_journal_path(root).exists())

    def test_interrupted_process_is_recovered_before_next_candidate(self):
        class SimulatedProcessExit(BaseException):
            pass

        with tempfile.TemporaryDirectory(prefix="ledger-interrupted-test-") as raw:
            root = Path(raw)
            paths, candidate = self.transaction_fixture(root)
            original = {relative: (root / relative).read_bytes() for relative in paths}

            def interrupt(stage, relative):
                if stage == "after_candidate_replace" and relative == "README.md":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                replace_tracked_files(root, candidate, failure_hook=interrupt)
            self.assertTrue(recovery_journal_path(root).is_dir())
            self.assertNotEqual(
                {relative: (root / relative).read_bytes() for relative in paths},
                original,
            )
            self.assertTrue(recover_incomplete_transaction(root))
            self.assertEqual(
                {relative: (root / relative).read_bytes() for relative in paths},
                original,
            )
            self.assertFalse(recovery_journal_path(root).exists())

    def test_exact_jsonl_line_bytes_are_the_record_hash_input(self):
        record = {"run_id": "fixture", "text": "é", "number": 1}
        line = canonical_json_line_bytes(record)
        self.assertEqual(line[-1:], b"\n")
        self.assertEqual(sha256_bytes(line), sha256_bytes(line))
        self.assertNotEqual(sha256_bytes(line), sha256_bytes(line[:-1] + b" "))

    def fixture_cleanup_tree(self, root: Path, *, batch_id="batch-cleanup-a005"):
        for relative in (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
            "schema/receipt.schema.json",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes().replace(b"\n", b"\n"))
        body = "retained source fixture"
        login = "".join(("fixture", "-author"))
        numeric_user_id = 7001
        association = "OWNER"
        created_at = "2026-07-29T10:00:00Z"
        updated_at = "2026-07-29T10:00:00Z"
        digest = safe_comment_body_hash(body)
        queue_snapshot_digest = sha256_bytes(
            canonical_json_bytes(
                [{
                    "id": 1,
                    "author_id": numeric_user_id,
                    "author_sha256": safe_author_hash(login),
                    "author_association": association,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "body_sha256": digest,
                }]
            )
        )
        hashes = {
            "evaluations_jsonl": sha256_bytes((root / "evaluations.jsonl").read_bytes()),
            "dispositions_jsonl": sha256_bytes((root / "ledger/dispositions.jsonl").read_bytes()),
            "readme_md": sha256_bytes((root / "README.md").read_bytes()),
            "scorecard_md": sha256_bytes((root / "scorecard.md").read_bytes()),
            "model_recommendation_json": sha256_bytes((root / "analysis/model-recommendation.json").read_bytes()),
        }
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
        candidate_manifest = git_tree_file_bindings(root, content_sha)
        candidate_manifest_sha = git_tree_manifest_sha256(candidate_manifest)
        batch = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": batch_id,
            "batch_mode": "initial",
            "controller_run_id": "controller-cleanup-a005",
            "source_replay": {"adapter": "github-intake-v1"},
            "base_sha": content_sha,
            "canonical_main_sha": content_sha,
            "candidate_content_commit_sha": content_sha,
            "pr_number": 151,
            "candidate_content_manifest": candidate_manifest,
            "candidate_content_manifest_sha256": candidate_manifest_sha,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "source_comment_watermark": 1,
            "full_queue_count": 1,
            "latest_observed_comment_id": 1,
            "latest_observed_update_time": "2026-07-29T10:00:00Z",
            "queue_snapshot_sha256": queue_snapshot_digest,
            "source_comment_ids": [1],
            "source_body_sha256": {"1": digest},
            "selected_comment_ids": [1],
            "selected_comment_count": 1,
            "terminal_outcome_count": 1,
            "terminal_outcomes": {
                "1": {
                    "outcome_code": "no_marker",
                    "evaluation_run_id": None,
                    "canonical_record_sha256": None,
                    "cleanup_eligible": False,
                }
            },
            "admitted_run_ids": [],
            "accepted_record_proofs": {},
            "canonical_record_hashes": {},
            "canonical_hashes": hashes,
            "comment_bindings": [
                {
                    "comment_id": 1,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "body_sha256": digest,
                    "outcome_code": "no_marker",
                    "evaluation_run_id": None,
                    "canonical_record_sha256": None,
                    "cleanup_eligible": False,
                }
            ],
        }
        receipt_path = root / "ledger" / "receipts" / "batches" / f"{batch_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(
            (json.dumps(batch, sort_keys=True, indent=2) + "\n").encode("utf-8")
        )
        subprocess.run(["git", "add", str(receipt_path)], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "receipt"], cwd=root, check=True)
        return body, batch

    def cleanup_config(self, root: Path, batch_id: str, *, receipt_status="unverified", merge_state="merged"):
        canonical_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return CleanupConfig(
            batch_id=batch_id,
            canonical_merge_sha=canonical_sha,
            canonical_main_sha=canonical_sha,
            expected_head_sha=canonical_sha,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="unreviewed",
            pr_state="closed",
            merge_state=merge_state,
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status=receipt_status,
            repository_root=root,
        )

    def authority_reader(self, config):
        return {
            "pr_state": config.pr_state,
            "merge_state": config.merge_state,
            "checks_state": config.checks_state,
            "review_state": config.review_state,
            "canonical_merge_sha": config.canonical_merge_sha,
            "expected_head_sha": config.expected_head_sha,
            "canonical_main_sha": config.canonical_main_sha,
            "recorded_receipt_status": config.recorded_receipt_status,
        }

    def commit_fixture_file(
        self,
        root: Path,
        relative: str,
        content: bytes,
        message: str,
    ) -> str:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def checkout_fixture_commit(self, root: Path, commit_sha: str) -> None:
        subprocess.run(
            ["git", "checkout", "--detach", commit_sha],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

    def ancestry_topology(self, root: Path, batch_id: str) -> dict[str, str]:
        self.fixture_cleanup_tree(root, batch_id=batch_id)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        merge_sha = self.commit_fixture_file(
            root,
            "transaction-authority.txt",
            b"accepted transaction\n",
            "transaction merge",
        )
        one_generation_sha = self.commit_fixture_file(
            root,
            "repair-authority.txt",
            b"one generation\n",
            "code-only repair",
        )
        multi_generation_sha = self.commit_fixture_file(
            root,
            "second-repair-authority.txt",
            b"multi generation\n",
            "second code-only repair",
        )
        self.checkout_fixture_commit(root, base_sha)
        sibling_sha = self.commit_fixture_file(
            root,
            "sibling-authority.txt",
            b"sibling main\n",
            "sibling main",
        )
        return {
            "batch_id": batch_id,
            "base": base_sha,
            "merge": merge_sha,
            "one": one_generation_sha,
            "multi": multi_generation_sha,
            "sibling": sibling_sha,
        }

    def topology_config(
        self,
        root: Path,
        topology: dict[str, str],
        merge_sha: str,
        main_sha: str,
        *,
        recorded_receipt_status: str = "absent",
    ) -> CleanupConfig:
        return CleanupConfig(
            batch_id=topology["batch_id"],
            canonical_merge_sha=merge_sha,
            canonical_main_sha=main_sha,
            expected_head_sha=topology["base"],
            pr_number=205,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="unreviewed",
            pr_state="closed",
            merge_state="merged",
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status=recorded_receipt_status,
            repository_root=root,
        )

    def prepare_topology(self, config: CleanupConfig) -> dict:
        with (
            mock.patch.object(cleanup_workflow, "_verify_raw_head_receipt_seal"),
            mock.patch.object(
                cleanup_workflow,
                "_retained_comment_evidence",
                return_value=([], True),
            ),
        ):
            return prepare_cleanup_receipt(
                config,
                authority_reader=self.authority_reader,
            )

    def test_commit_ancestry_matrix_uses_real_git_and_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="ledger-ancestry-matrix-") as raw:
            root = Path(raw)
            topology = self.ancestry_topology(
                root,
                "batch-ancestry-matrix-a5",
            )
            self.assertTrue(
                _is_commit_ancestor(root, topology["merge"], topology["merge"])
            )
            self.assertTrue(
                _is_commit_ancestor(root, topology["merge"], topology["one"])
            )
            self.assertTrue(
                _is_commit_ancestor(root, topology["merge"], topology["multi"])
            )
            self.assertFalse(
                _is_commit_ancestor(root, topology["merge"], topology["sibling"])
            )
            self.assertFalse(
                _is_commit_ancestor(root, topology["sibling"], topology["merge"])
            )
            self.assertFalse(
                _is_commit_ancestor(root, topology["multi"], topology["base"])
            )
            self.assertFalse(
                _is_commit_ancestor(root, "0" * 40, topology["multi"])
            )

            with mock.patch(
                "scripts.processor.cleanup_workflow.subprocess.run",
                side_effect=OSError("git unavailable"),
            ):
                self.assertFalse(
                    _is_commit_ancestor(root, topology["merge"], topology["one"])
                )
            with mock.patch(
                "scripts.processor.cleanup_workflow.subprocess.run",
                return_value=subprocess.CompletedProcess(["git"], 2),
            ):
                self.assertFalse(
                    _is_commit_ancestor(root, topology["merge"], topology["one"])
                )

    def test_postmerge_ancestry_finality_matrix_preserves_data_and_receipt_authority(self):
        with tempfile.TemporaryDirectory(prefix="ledger-ancestry-finality-") as raw:
            root = Path(raw)
            topology = self.ancestry_topology(
                root,
                "batch-ancestry-finality-a5",
            )

            def prepare_for(merge_sha: str, main_sha: str):
                self.checkout_fixture_commit(root, main_sha)
                config = self.topology_config(root, topology, merge_sha, main_sha)
                return config, self.prepare_topology(config)

            equal_config, equal_receipt = prepare_for(
                topology["merge"],
                topology["merge"],
            )
            self.assertEqual(equal_receipt["cleanup_status"], "verified")
            self.assertTrue(_receipt_matches_authority(equal_receipt, equal_config))

            descendant_config, descendant_receipt = prepare_for(
                topology["merge"],
                topology["one"],
            )
            self.assertEqual(descendant_receipt["cleanup_status"], "verified")
            self.assertEqual(
                descendant_receipt["canonical_merge_sha"],
                topology["merge"],
            )
            self.assertEqual(
                descendant_receipt["canonical_main_sha"],
                topology["one"],
            )
            self.assertTrue(
                _receipt_matches_authority(descendant_receipt, descendant_config)
            )
            recorded_comment = {
                "id": 991,
                "issue_url": RECEIPT_ISSUE_ENDPOINT,
                "body": (
                    RECORDED_MARKER
                    + "\n"
                    + canonical_json_bytes(descendant_receipt).decode("utf-8")
                ),
            }
            self.assertEqual(
                _recorded_receipt_status(descendant_config, [recorded_comment]),
                "present_matching",
            )

            multi_config, multi_receipt = prepare_for(
                topology["merge"],
                topology["multi"],
            )
            self.assertEqual(multi_receipt["cleanup_status"], "verified")
            self.assertTrue(_receipt_matches_authority(multi_receipt, multi_config))

            sibling_config, sibling_receipt = prepare_for(
                topology["merge"],
                topology["sibling"],
            )
            self.assertEqual(sibling_receipt["cleanup_status"], "blocked")
            self.assertEqual(
                sibling_receipt["branch_cleanup_reason"],
                "canonical_unverified",
            )
            self.assertFalse(
                _receipt_matches_authority(sibling_receipt, sibling_config)
            )

            reverse_config, reverse_receipt = prepare_for(
                topology["multi"],
                topology["base"],
            )
            self.assertEqual(reverse_receipt["cleanup_status"], "blocked")
            self.assertEqual(
                reverse_receipt["branch_cleanup_reason"],
                "canonical_unverified",
            )
            missing_config, missing_receipt = prepare_for(
                "0" * 40,
                topology["multi"],
            )
            self.assertEqual(missing_receipt["cleanup_status"], "blocked")
            self.assertEqual(
                missing_receipt["branch_cleanup_reason"],
                "canonical_unverified",
            )

            self.checkout_fixture_commit(root, topology["merge"])
            changed_data_sha = self.commit_fixture_file(
                root,
                "README.md",
                (root / "README.md").read_bytes() + b"post-merge generated change\n",
                "invalid canonical generated data",
            )
            self.assertTrue(
                _is_commit_ancestor(root, topology["merge"], changed_data_sha)
            )
            changed_config, changed_receipt = prepare_for(
                topology["merge"],
                changed_data_sha,
            )
            self.assertEqual(changed_receipt["cleanup_status"], "blocked")
            self.assertEqual(
                changed_receipt["branch_cleanup_reason"],
                "canonical_unverified",
            )

            self.checkout_fixture_commit(root, topology["merge"])
            invalid_batch_sha = self.commit_fixture_file(
                root,
                f"ledger/receipts/batches/{topology['batch_id']}.json",
                b"not a batch receipt\n",
                "invalid batch receipt",
            )
            invalid_config = self.topology_config(
                root,
                topology,
                topology["merge"],
                invalid_batch_sha,
            )
            with self.assertRaises(ProcessorError) as raised:
                self.prepare_topology(invalid_config)
            self.assertEqual(
                raised.exception.code,
                "processor_cleanup_batch_unavailable",
            )

            forged_config = self.topology_config(
                root,
                topology,
                topology["sibling"],
                topology["one"],
            )
            forged_receipt = copy.deepcopy(descendant_receipt)
            forged_receipt["canonical_merge_sha"] = topology["sibling"]
            self.assertFalse(
                _receipt_matches_authority(forged_receipt, forged_config)
            )

            def live_authority(main_sha: str, merge_sha: str):
                config = self.topology_config(root, topology, merge_sha, main_sha)
                pr = {
                    "state": "closed",
                    "merged_at": "2026-08-21T00:00:00Z",
                    "merge_commit_sha": merge_sha,
                    "head": {"sha": topology["base"]},
                }
                main = {"object": {"sha": main_sha}}
                raw_commit = {
                    "parents": [{"sha": topology["base"]}],
                    "files": [],
                }
                raw_receipt = {
                    "type": "file",
                    "encoding": "base64",
                    "content": "e30=",
                }
                with (
                    mock.patch.object(
                        cleanup_workflow,
                        "_gh_get_json",
                        side_effect=[
                            pr,
                            main,
                            raw_commit,
                            raw_receipt,
                            {"workflow_runs": []},
                        ],
                    ),
                    mock.patch.object(
                        cleanup_workflow,
                        "_gh_get_paginated",
                        side_effect=[[], []],
                    ),
                    mock.patch.object(
                        cleanup_workflow,
                        "_gh_get_threads",
                        return_value=[],
                    ),
                ):
                    return _readback_live_authority(config)

            for main_sha in (
                topology["merge"],
                topology["one"],
                topology["multi"],
            ):
                with self.subTest(main_sha=main_sha):
                    authority = live_authority(main_sha, topology["merge"])
                    self.assertEqual(authority["merge_state"], "merged")
                    self.assertEqual(
                        authority["canonical_merge_sha"],
                        topology["merge"],
                    )
                    self.assertEqual(authority["canonical_main_sha"], main_sha)
            self.assertEqual(
                live_authority(topology["sibling"], topology["merge"])["merge_state"],
                "unmerged",
            )
            self.assertEqual(
                live_authority(topology["base"], topology["multi"])["merge_state"],
                "unmerged",
            )
            self.assertEqual(
                live_authority(topology["multi"], "0" * 40)["merge_state"],
                "unmerged",
            )

    def test_cleanup_preparation_uses_manifest_backed_authority_in_real_clone(self):
        batch_id = "batch-run190-fresh-clone-fixture"
        receipt_relative = f"ledger/receipts/batches/{batch_id}.json"
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-fresh-clone-") as raw:
            workspace = Path(raw)
            source = workspace / "source"
            canonical = workspace / "canonical"
            negative = workspace / "negative"
            source.mkdir()
            canonical_files = {
                "evaluations.jsonl": b"",
                "ledger/dispositions.jsonl": b"[]\n",
                "README.md": b"run190 fixture\n",
                "scorecard.md": b"run190 fixture\n",
                "analysis/model-recommendation.json": b"{}\n",
            }
            for relative, content in canonical_files.items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            schema_path = source / "schema" / "receipt.schema.json"
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_bytes(
                (ROOT / "schema" / "receipt.schema.json")
                .read_bytes()
                .replace(b"\n", b"\n")
            )

            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=source, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture" + "@" + "example.invalid"],
                cwd=source,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "fixture"], cwd=source, check=True)
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=source, check=True)
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            subprocess.run(["git", "branch", "candidate"], cwd=source, check=True)
            subprocess.run(["git", "checkout", "-q", "candidate"], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-qm", "historical candidate"],
                cwd=source,
                check=True,
            )
            candidate_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            subprocess.run(["git", "checkout", "-q", "main"], cwd=source, check=True)

            body = "fresh-clone source fixture"
            created_at = "2026-08-21T00:00:00Z"
            digest = safe_comment_body_hash(body)
            queue_snapshot = sha256_bytes(
                canonical_json_bytes(
                    [
                        {
                            "id": 1,
                            "author_id": 7001,
                            "author_sha256": safe_author_hash("fixture-author"),
                            "author_association": "OWNER",
                            "created_at": created_at,
                            "updated_at": created_at,
                            "body_sha256": digest,
                        }
                    ]
                )
            )
            canonical_hashes = {
                name: sha256_bytes((source / relative).read_bytes())
                for name, relative in CANONICAL_PATHS.items()
            }
            candidate_manifest = git_tree_file_bindings(source, candidate_sha)
            candidate_manifest_sha = git_tree_manifest_sha256(candidate_manifest)
            batch = {
                "schema_version": 2,
                "receipt_type": "batch",
                "batch_id": batch_id,
                "batch_mode": "initial",
                "controller_run_id": "controller-run190-fresh-clone-fixture",
                "base_sha": base_sha,
                "canonical_main_sha": base_sha,
                "candidate_content_commit_sha": candidate_sha,
                "candidate_content_manifest": candidate_manifest,
                "candidate_content_manifest_sha256": candidate_manifest_sha,
                "source_replay": {"adapter": "github-intake-v1"},
                "pr_number": 207,
                "source_issue_number": 142,
                "receipt_issue_number": 143,
                "source_comment_watermark": 1,
                "full_queue_count": 1,
                "latest_observed_comment_id": 1,
                "latest_observed_update_time": created_at,
                "queue_snapshot_sha256": queue_snapshot,
                "source_comment_ids": [1],
                "source_body_sha256": {"1": digest},
                "selected_comment_ids": [1],
                "selected_comment_count": 1,
                "terminal_outcome_count": 1,
                "terminal_outcomes": {
                    "1": {
                        "outcome_code": "no_marker",
                        "evaluation_run_id": None,
                        "canonical_record_sha256": None,
                        "cleanup_eligible": False,
                    }
                },
                "admitted_run_ids": [],
                "accepted_record_proofs": {},
                "canonical_record_hashes": {},
                "canonical_hashes": canonical_hashes,
                "comment_bindings": [
                    {
                        "comment_id": 1,
                        "created_at": created_at,
                        "updated_at": created_at,
                        "body_sha256": digest,
                        "outcome_code": "no_marker",
                        "evaluation_run_id": None,
                        "canonical_record_sha256": None,
                        "cleanup_eligible": False,
                    }
                ],
            }
            receipt_path = source / receipt_relative
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(
                (json.dumps(batch, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
            )
            subprocess.run(["git", "add", receipt_relative], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "canonical receipt"], cwd=source, check=True)
            canonical_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            subprocess.run(["git", "branch", "historical-seal"], cwd=source, check=True)
            subprocess.run(["git", "checkout", "-q", "historical-seal"], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-qm", "historical seal"],
                cwd=source,
                check=True,
            )
            historical_seal_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            subprocess.run(["git", "checkout", "-q", "main"], cwd=source, check=True)

            self.assertEqual(
                subprocess.run(
                    ["git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"],
                    cwd=source,
                    check=False,
                ).returncode,
                0,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "cat-file", "-e", f"{historical_seal_sha}^{{commit}}"],
                    cwd=source,
                    check=False,
                ).returncode,
                0,
            )
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-local",
                    "--no-hardlinks",
                    "--branch",
                    "main",
                    "--single-branch",
                    "--no-tags",
                    "--no-checkout",
                    str(source),
                    str(canonical),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=canonical, check=True)
            subprocess.run(
                ["git", "checkout", "--detach", canonical_sha],
                cwd=canonical,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"],
                    cwd=canonical,
                    check=False,
                ).returncode,
                0,
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "cat-file", "-e", f"{historical_seal_sha}^{{commit}}"],
                    cwd=canonical,
                    check=False,
                ).returncode,
                0,
            )

            receipt_bytes = (canonical / receipt_relative).read_bytes()
            canonical_batch = json.loads(receipt_bytes.decode("utf-8"))
            with self.assertRaises(ReceiptValidationError):
                validate_batch_receipt_object(
                    canonical,
                    canonical_batch,
                    authority_sha=canonical_sha,
                )

            def config_for(root, main_sha, expected_head_sha):
                return CleanupConfig(
                    batch_id=batch_id,
                    canonical_merge_sha=main_sha,
                    canonical_main_sha=main_sha,
                    expected_head_sha=expected_head_sha,
                    pr_number=207,
                    source_issue_number=142,
                    receipt_issue_number=143,
                    activation_mode="dry-run",
                    operator_intent="unreviewed",
                    pr_state="closed",
                    merge_state="merged",
                    checks_state="passed",
                    review_state="clear",
                    recorded_receipt_status="absent",
                    repository_root=root,
                )

            def authority_for(config, current_batch, current_bytes):
                return {
                    "pr_state": config.pr_state,
                    "merge_state": config.merge_state,
                    "checks_state": config.checks_state,
                    "review_state": config.review_state,
                    "canonical_merge_sha": config.canonical_merge_sha,
                    "expected_head_sha": config.expected_head_sha,
                    "canonical_main_sha": config.canonical_main_sha,
                    "recorded_receipt_status": config.recorded_receipt_status,
                    "raw_head_parent_shas": [
                        current_batch["candidate_content_commit_sha"]
                    ],
                    "raw_head_changed_paths": [receipt_relative],
                    "raw_head_receipt_sha256": sha256_bytes(current_bytes),
                }

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": created_at,
                    "updated_at": created_at,
                }

            config = config_for(canonical, canonical_sha, historical_seal_sha)
            receipt = prepare_cleanup_receipt(
                config,
                fetcher=fetcher,
                authority_reader=lambda current: authority_for(
                    current,
                    canonical_batch,
                    receipt_bytes,
                ),
            )
            self.assertEqual(receipt["cleanup_status"], "verified")
            self.assertEqual(receipt["branch_cleanup_reason"], "receipt_unverified")

            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-local",
                    "--no-hardlinks",
                    "--branch",
                    "main",
                    "--single-branch",
                    "--no-tags",
                    str(source),
                    str(negative),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=negative, check=True)
            subprocess.run(["git", "checkout", "--force", "main"], cwd=negative, check=True)
            negative_receipt_path = negative / receipt_relative
            negative_batch = json.loads(negative_receipt_path.read_text(encoding="utf-8"))
            negative_batch["candidate_content_manifest"].pop()
            negative_receipt_path.write_bytes(
                (
                    json.dumps(
                        negative_batch,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n"
                ).encode("utf-8")
            )
            subprocess.run(["git", "config", "user.email", "fixture" + "@" + "example.invalid"], cwd=negative, check=True)
            subprocess.run(["git", "config", "user.name", "fixture"], cwd=negative, check=True)
            subprocess.run(["git", "add", receipt_relative], cwd=negative, check=True)
            subprocess.run(["git", "commit", "-qm", "invalid manifest"], cwd=negative, check=True)
            negative_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=negative,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            negative_bytes = negative_receipt_path.read_bytes()
            negative_config = config_for(negative, negative_sha, historical_seal_sha)
            with self.assertRaises(ProcessorError) as raised:
                prepare_cleanup_receipt(
                    negative_config,
                    fetcher=fetcher,
                    authority_reader=lambda current: authority_for(
                        current,
                        negative_batch,
                        negative_bytes,
                    ),
                )
            self.assertEqual(raised.exception.code, "processor_cleanup_batch_unavailable")

    def test_cleanup_verifies_retention_and_stays_pending_without_receipt_proof(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root)

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            result = run_cleanup(
                self.cleanup_config(root, "batch-cleanup-a005"),
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(result["source_comments_retained"])
            self.assertFalse(result["publication_attempted"])
            self.assertEqual(result["receipt"]["branch_cleanup_reason"], "receipt_unverified")

    def test_verified_cleanup_can_reach_injected_future_publication_only_when_reviewed(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-live-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root, batch_id="batch-cleanup-live-a005")

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            config = self.cleanup_config(root, "batch-cleanup-live-a005", receipt_status="absent")
            receipt = prepare_cleanup_receipt(
                config,
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            self.assertEqual(receipt["cleanup_status"], "verified")

            def assert_no_raw_identity(value):
                if isinstance(value, Mapping):
                    for key, nested in value.items():
                        self.assertNotIn(key, {"author_id", "author_association"})
                        assert_no_raw_identity(nested)
                elif isinstance(value, (list, tuple)):
                    for nested in value:
                        assert_no_raw_identity(nested)
                elif isinstance(value, str):
                    self.assertNotIn(value, {"fixture-author", "7001"})
                elif type(value) is int:
                    self.assertNotEqual(value, 7001)

            collision_sha = "a" * 17 + "7001" + "b" * 19
            self.assertEqual(len(collision_sha), 40)
            self.assertNotEqual(collision_sha, "7001")
            assert_no_raw_identity({"nested": [{"canonical_sha": collision_sha}]})
            assert_no_raw_identity(receipt)

            negative_controls = {
                "raw_login": {"nested": [{"value": "fixture-author"}]},
                "raw_numeric_id": {"nested": [7001]},
                "raw_string_id": {"nested": ({"value": "7001"},)},
                "author_id_key": {"nested": [{"author_id": "redacted"}]},
                "author_association_key": {
                    "nested": [{"details": {"author_association": "redacted"}}]
                },
            }
            for label, value in negative_controls.items():
                with self.subTest(label=label):
                    with self.assertRaises(AssertionError):
                        assert_no_raw_identity(value)
            calls = []

            def publisher(body):
                calls.append(body)
                return 991

            def readback(locator):
                return {
                    "id": locator,
                    "body": calls[0],
                    "issue_url": RECEIPT_ISSUE_ENDPOINT,
                }

            published = publish_cleanup_receipt(
                receipt,
                activation_mode="reviewed-live",
                operator_intent="reviewed",
                publisher=publisher,
                readback=readback,
                comments_reader=lambda: [readback(991)],
                authority_verifier=lambda value: value == receipt,
            )
            self.assertEqual(published["status"], "published")
            self.assertEqual(len(calls), 1)
            with self.assertRaises(Exception):
                publish_cleanup_receipt(
                    receipt,
                    activation_mode="dry-run",
                    operator_intent="unreviewed",
                )

    def test_compact_cleanup_receipt_binds_immutable_batch_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-compact-contract-") as raw:
            root = Path(raw)
            body, batch = self.fixture_cleanup_tree(
                root,
                batch_id="batch-cleanup-compact-contract-a005",
            )
            fetched_ids = []

            def fetcher(comment_id, _root):
                fetched_ids.append(comment_id)
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            config = self.cleanup_config(
                root,
                "batch-cleanup-compact-contract-a005",
                receipt_status="absent",
            )
            receipt = prepare_cleanup_receipt(
                config,
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            receipt_path = root / "ledger/receipts/batches/batch-cleanup-compact-contract-a005.json"
            receipt_bytes = receipt_path.read_bytes()
            blob_sha = subprocess.run(
                ["git", "rev-parse", f"HEAD:{receipt_path.relative_to(root).as_posix()}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            self.assertEqual(fetched_ids, batch["source_comment_ids"])
            self.assertTrue(RECEIPT_VALIDATOR.is_valid(receipt))
            self.assertEqual(receipt["batch_receipt_blob_sha"], blob_sha)
            self.assertEqual(receipt["batch_receipt_sha256"], sha256_bytes(receipt_bytes))
            self.assertEqual(receipt["batch_receipt_bytes_sha256"], sha256_bytes(receipt_bytes))
            self.assertEqual(receipt["queue_snapshot_sha256"], batch["queue_snapshot_sha256"])
            self.assertEqual(receipt["source_comment_count"], len(batch["source_comment_ids"]))
            self.assertEqual(receipt["admitted_record_count"], len(batch["admitted_run_ids"]))
            removed_fields = (
                "canonical_record_hashes",
                "canonical_record_proofs",
                "source_comment_ids",
                "source_body_sha256",
                "retained_comment_ids",
            )
            for field in removed_fields:
                with self.subTest(removed_field=field):
                    self.assertNotIn(field, receipt)
                    if field == "canonical_record_proofs":
                        self.assertIn("accepted_record_proofs", batch)
                    elif field == "retained_comment_ids":
                        self.assertNotIn(field, batch)
                    else:
                        self.assertIn(field, batch)
                    self.assertTrue(RECEIPT_VALIDATOR.is_valid(batch))
                    invalid = copy.deepcopy(receipt)
                    invalid[field] = {} if field.endswith("hashes") or field.endswith("proofs") else []
                    self.assertFalse(RECEIPT_VALIDATOR.is_valid(invalid))
                    invalid_body = RECORDED_MARKER + "\n" + canonical_json_bytes(invalid).decode("utf-8")
                    with self.assertRaises(ProcessorError) as raised:
                        _parse_recorded_receipt_body(invalid_body)
                    self.assertEqual(raised.exception.code, "processor_cleanup_receipt_invalid")

            tampered_bindings = {
                "canonical_main_sha": "0" * 40,
                "batch_receipt_blob_sha": "0" * 40,
                "batch_receipt_sha256": "0" * 64,
                "batch_receipt_bytes_sha256": "0" * 64,
                "queue_snapshot_sha256": "0" * 64,
                "source_comment_count": receipt["source_comment_count"] + 1,
                "admitted_record_count": receipt["admitted_record_count"] + 1,
            }
            for field, value in tampered_bindings.items():
                with self.subTest(tampered_binding=field):
                    tampered = copy.deepcopy(receipt)
                    tampered[field] = value
                    self.assertFalse(_receipt_matches_authority(tampered, config))

            self.assertTrue(_receipt_matches_authority(receipt, config))
            for field in sorted(receipt["canonical_hashes"]):
                with self.subTest(canonical_hash=field):
                    tampered = copy.deepcopy(receipt)
                    replacement = "0" * 64
                    if replacement == tampered["canonical_hashes"][field]:
                        replacement = "1" * 64
                    tampered["canonical_hashes"][field] = replacement
                    self.assertFalse(_receipt_matches_authority(tampered, config))

            snapshot_mutations = {
                "recorded_receipt_status": "present_matching",
                "branch_cleanup_eligible": True,
                "branch_cleanup_reason": "eligible",
                "publication_status": "published",
                "platform_limitation_code": "none",
            }
            for field, replacement in snapshot_mutations.items():
                with self.subTest(snapshot_field=field):
                    tampered = copy.deepcopy(receipt)
                    tampered[field] = replacement
                    self.assertFalse(_receipt_matches_authority(tampered, config))

            def recorded_comment(value, comment_id):
                return {
                    "id": comment_id,
                    "issue_url": RECEIPT_ISSUE_ENDPOINT,
                    "body": RECORDED_MARKER
                    + "\n"
                    + canonical_json_bytes(value).decode("utf-8"),
                }

            self.assertEqual(_recorded_receipt_status(config, []), "absent")
            exact_comment = recorded_comment(receipt, 991)
            self.assertEqual(
                _recorded_receipt_status(config, [exact_comment]),
                "present_matching",
            )
            self.assertEqual(
                _recorded_receipt_status(
                    config,
                    [exact_comment, recorded_comment(receipt, 992)],
                ),
                "conflicting",
            )
            forged = copy.deepcopy(receipt)
            forged["canonical_hashes"]["evaluations_jsonl"] = "f" * 64
            forged_comment = recorded_comment(forged, 993)
            self.assertEqual(
                _recorded_receipt_status(config, [forged_comment]),
                "conflicting",
            )

    def test_compact_publication_size_gate_roundtrips_and_fails_before_publisher(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-compact-publication-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(
                root,
                batch_id="batch-cleanup-compact-publication-a005",
            )

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            receipt = prepare_cleanup_receipt(
                self.cleanup_config(
                    root,
                    "batch-cleanup-compact-publication-a005",
                    receipt_status="absent",
                ),
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            scaled = copy.deepcopy(receipt)
            scaled["source_comment_count"] = 806
            scaled["admitted_record_count"] = 120
            intended_bytes = (
                RECORDED_MARKER.encode("utf-8")
                + b"\n"
                + canonical_json_bytes(scaled)
            )
            intended_body = intended_bytes.decode("utf-8")
            self.assertTrue(intended_bytes.startswith(RECORDED_MARKER.encode("utf-8")))
            self.assertEqual(_parse_recorded_receipt_body(intended_body), scaled)
            self.assertLess(len(intended_body), RECORDED_COMMENT_MAX_CHARS)
            self.assertLess(len(intended_bytes), RECORDED_COMMENT_MAX_CHARS)

            calls = []

            def publisher(value):
                calls.append(value)
                return 991

            def readback(locator):
                return {
                    "id": locator,
                    "body": calls[0],
                    "issue_url": RECEIPT_ISSUE_ENDPOINT,
                }

            published = publish_cleanup_receipt(
                scaled,
                activation_mode="reviewed-live",
                operator_intent="reviewed",
                publisher=publisher,
                readback=readback,
                comments_reader=lambda: [readback(991)],
                authority_verifier=lambda value: value == scaled,
            )
            self.assertEqual(published["status"], "published")
            self.assertEqual(calls, [intended_body])

            oversized_cases = {
                "characters": "a" * (RECORDED_COMMENT_MAX_CHARS + 100),
                "utf8_bytes": "é" * 40000,
            }
            for label, oversized_batch_id in oversized_cases.items():
                with self.subTest(oversized=label):
                    oversized = copy.deepcopy(scaled)
                    oversized["batch_id"] = oversized_batch_id
                    before_calls = len(calls)
                    with self.assertRaises(ProcessorError) as raised:
                        publish_cleanup_receipt(
                            oversized,
                            activation_mode="reviewed-live",
                            operator_intent="reviewed",
                            publisher=publisher,
                        )
                    self.assertEqual(
                        raised.exception.code,
                        "processor_cleanup_receipt_too_large",
                    )
                    self.assertEqual(len(calls), before_calls)

    def test_cleanup_reads_immutable_objects_when_worktree_is_hostile(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-object-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root, batch_id="batch-cleanup-object-a005")
            config = self.cleanup_config(root, "batch-cleanup-object-a005", receipt_status="absent")
            original = (root / "evaluations.jsonl").read_bytes()
            altered = b'{"test_only":"hostile_worktree"}\n'
            self.assertNotEqual(original, altered)
            (root / "evaluations.jsonl").write_bytes(altered)

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                    "author_association": "OWNER",
                    "body": body,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
                }

            receipt = prepare_cleanup_receipt(
                config,
                fetcher=fetcher,
                authority_reader=self.authority_reader,
            )
            self.assertEqual(receipt["cleanup_status"], "verified")
            self.assertEqual(receipt["canonical_hashes"]["evaluations_jsonl"], sha256_bytes(original))
            self.assertNotEqual(receipt["canonical_hashes"]["evaluations_jsonl"], sha256_bytes(altered))


    def test_cleanup_retention_requires_exact_complete_source_identity(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-identity-matrix-") as raw:
            root = Path(raw)
            body, batch = self.fixture_cleanup_tree(
                root,
                batch_id="batch-cleanup-identity-matrix-a005",
            )
            base_comment = {
                "id": 1,
                "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                "author_association": "OWNER",
                "body": body,
                "created_at": "2026-07-29T10:00:00Z",
                "updated_at": "2026-07-29T10:00:00Z",
            }

            def retained(comment):
                return _retained_comment_evidence(
                    batch,
                    root,
                    lambda _comment_id, _root: comment,
                )[1]

            mutations = {
                "numeric_id": lambda value: value["user"].update(id=7002),
                "login": lambda value: value["user"].__setitem__("l" + "ogin", "other"),
                "association": lambda value: value.update(author_association="MEMBER"),
                "created_at": lambda value: value.update(created_at="2026-07-29T11:00:00Z"),
                "updated_at": lambda value: value.update(updated_at="2026-07-29T11:00:00Z"),
                "body": lambda value: value.update(body="changed"),
                "comment_id": lambda value: value.update(id=2),
                "bool_user_id": lambda value: value["user"].update(id=True),
                "zero_user_id": lambda value: value["user"].update(id=0),
                "negative_user_id": lambda value: value["user"].update(id=-1),
                "empty_login": lambda value: value["user"].__setitem__("l" + "ogin", ""),
                "malformed_login": lambda value: value["user"].__setitem__("l" + "ogin", "not valid"),
                "empty_association": lambda value: value.update(author_association=""),
                "malformed_association": lambda value: value.update(author_association=7),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    comment = copy.deepcopy(base_comment)
                    mutate(comment)
                    self.assertFalse(retained(comment))

            with self.subTest(label="missing_comment"):
                def missing(_comment_id, _root):
                    raise ProcessorError("processor_source_unavailable")
                self.assertFalse(
                    _retained_comment_evidence(batch, root, missing)[1]
                )

            with self.subTest(label="snapshot_mismatch"):
                mismatched = copy.deepcopy(batch)
                mismatched["queue_snapshot_sha256"] = "0" * 64
                result = _retained_comment_evidence(
                    mismatched,
                    root,
                    lambda _comment_id, _root: copy.deepcopy(base_comment),
                )
                self.assertFalse(result[1])

            retained_ids, verified = _retained_comment_evidence(
                batch,
                root,
                lambda _comment_id, _root: copy.deepcopy(base_comment),
            )
            self.assertEqual(retained_ids, [1])
            self.assertTrue(verified)

    def test_check_runs_are_bound_to_raw_pr_head(self):
        root = Path(tempfile.gettempdir())
        raw_head = "c" * 40
        config = CleanupConfig(
            batch_id="batch-check-head-a005",
            canonical_merge_sha="a" * 40,
            canonical_main_sha="a" * 40,
            expected_head_sha=raw_head,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="unreviewed",
            pr_state="closed",
            merge_state="merged",
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status="absent",
            repository_root=root,
        )
        pr = {
            "state": "closed",
            "merged_at": "2026-07-30T00:00:00Z",
            "merge_commit_sha": "a" * 40,
            "head": {"sha": raw_head},
        }
        main = {"object": {"sha": "a" * 40}}
        raw_commit = {
            "parents": [{"sha": "b" * 40}],
            "files": [{"filename": "ledger/receipts/batches/batch-check-head-a005.json"}],
        }
        raw_receipt = {
            "type": "file",
            "encoding": "base64",
            "content": "e30=",
        }
        with (
            mock.patch(
                "scripts.processor.cleanup_workflow._gh_get_json",
                side_effect=[pr, main, raw_commit, raw_receipt, {"workflow_runs": []}],
            ) as json_calls,
            mock.patch(
                "scripts.processor.cleanup_workflow._gh_get_paginated",
                side_effect=[[], []],
            ),
            mock.patch("scripts.processor.cleanup_workflow._gh_get_threads", return_value=[]),
        ):
            authority = _readback_live_authority(config)
        self.assertEqual(authority["checks_state"], "incomplete")
        self.assertIn(raw_head, json_calls.call_args_list[4].args[0])

    def test_publication_never_trusts_adapter_without_exact_unique_readback(self):
        receipt = {
            "cleanup_status": "verified",
            "recorded_receipt_status": "absent",
        }
        captured = []

        def publisher(body):
            captured.append(body)
            return 81

        cases = (
            (
                lambda _locator: {"id": 81, "body": "mismatch", "issue_url": "https://api.github.test/issues/143"},
                lambda: [],
                lambda _value: True,
            ),
            (
                lambda _locator: {"id": 81, "body": captured[0], "issue_url": "https://api.github.test/issues/143"},
                lambda: [
                    {"id": 81, "body": captured[0]},
                    {"id": 82, "body": captured[0]},
                ],
                lambda _value: True,
            ),
            (
                lambda _locator: {"id": 81, "body": captured[0], "issue_url": "https://api.github.test/issues/143"},
                lambda: [{"id": 81, "body": captured[0]}],
                lambda _value: False,
            ),
        )
        for readback, comments_reader, verifier in cases:
            captured.clear()
            result = publish_cleanup_receipt(
                receipt,
                activation_mode="reviewed-live",
                operator_intent="reviewed",
                publisher=publisher,
                readback=readback,
                comments_reader=comments_reader,
                authority_verifier=verifier,
            )
            self.assertEqual(result["status"], "PENDING_OPERATOR_PUBLICATION")


class TestRepositoryPathContainment(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        (root / "nested" / "deep").mkdir(parents=True)
        (root / "nested" / "deep" / "tracked.txt").write_bytes(b"inside\n")
        (root / "target.txt").write_bytes(b"inside-target\n")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "fixture" + "@" + "example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "fixture"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)

    def symlink_or_skip(self, target: Path, link: Path, *, directory: bool) -> None:
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links unavailable: {type(error).__name__}")

    def test_ambiguous_or_redirecting_lexical_paths_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-lexical-") as raw:
            root = Path(raw)
            self.make_repo(root)
            guard = RepositoryPathGuard(root)
            for unsafe in (
                "../outside",
                "nested\\deep\\tracked.txt",
                "/absolute",
                "C:/absolute",
                "nested//deep/tracked.txt",
                "nested/./deep/tracked.txt",
                "nested/file.txt:stream",
                "nested:stream/file.txt",
                "nested/deep/file.txt:stream",
                "nested/deep:stream/file.txt",
            ):
                with self.assertRaises(ProcessorError, msg=unsafe):
                    guard.path(unsafe)
            self.assertEqual(
                root / "nested" / "deep" / "tracked.txt",
                guard.path(
                    "nested/deep/tracked.txt",
                    leaf_may_be_missing=False,
                ),
            )

    def test_colon_paths_fail_before_snapshot_prepare_or_replacement(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-colon-") as raw:
            root = Path(raw)
            self.make_repo(root)
            guard = RepositoryPathGuard(root)
            original = (root / "nested" / "deep" / "tracked.txt").read_bytes()
            unsafe_paths = (
                "nested/file.txt:stream",
                "nested:stream/file.txt",
                "nested/deep/file.txt:stream",
                "nested/deep:stream/file.txt",
            )
            for unsafe in unsafe_paths:
                with self.subTest(path=unsafe):
                    with self.assertRaises(ProcessorError):
                        guard.prepare(unsafe)
                    with self.assertRaises(ProcessorError):
                        snapshot_tracked_files(root, (unsafe,))
                    with self.assertRaises(ProcessorError):
                        replace_tracked_files(root, {unsafe: b"candidate\n"})
                    self.assertEqual(
                        original,
                        (root / "nested" / "deep" / "tracked.txt").read_bytes(),
                    )
                    self.assertFalse(recovery_journal_path(root).exists())

    def test_recovery_rejects_colons_in_target_and_snapshot_before_mutation(self):
        class SimulatedProcessExit(BaseException):
            pass

        with tempfile.TemporaryDirectory(prefix="ledger-path-colon-recovery-") as raw:
            root = Path(raw)
            self.make_repo(root)

            def interrupt(stage, relative):
                if (
                    stage == "after_candidate_replace"
                    and relative == "nested/deep/tracked.txt"
                ):
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                replace_tracked_files(
                    root,
                    {"nested/deep/tracked.txt": b"candidate\n"},
                    failure_hook=interrupt,
                )
            journal = recovery_journal_path(root)
            manifest_path = journal / "manifest.json"
            original_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            candidate = (root / "nested" / "deep" / "tracked.txt")
            self.assertEqual(b"candidate\n", candidate.read_bytes())

            corruptions = (
                ("path", "nested/deep/tracked.txt:stream"),
                ("path", "nested/deep:stream/tracked.txt"),
                ("snapshot", "0000.snapshot:stream"),
            )
            for field, value in corruptions:
                with self.subTest(field=field, value=value):
                    manifest = copy.deepcopy(original_manifest)
                    manifest["targets"][0][field] = value
                    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
                    manifest_path.write_bytes(manifest_bytes)
                    with self.assertRaises(ProcessorError):
                        recover_incomplete_transaction(root)
                    self.assertEqual(manifest_bytes, manifest_path.read_bytes())
                    self.assertEqual(b"candidate\n", candidate.read_bytes())

    @unittest.skipIf(os.name == "nt", "POSIX-specific symlink escape")
    def test_posix_symlink_parent_escape_and_nested_redirect_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-posix-") as raw:
            root = Path(raw) / "repo"
            outside = Path(raw) / "outside"
            root.mkdir()
            outside.mkdir()
            self.make_repo(root)
            (root / "nested" / "deep" / "tracked.txt").unlink()
            (root / "nested" / "deep").rmdir()
            self.symlink_or_skip(outside, root / "nested" / "deep", directory=True)
            guard = RepositoryPathGuard(root)
            with self.assertRaises(ProcessorError):
                guard.path("nested/deep/tracked.txt")
            with self.assertRaises(ProcessorError):
                replace_tracked_files(
                    root,
                    {"nested/deep/tracked.txt": b"candidate\n"},
                )

    def test_symlink_target_file_is_rejected_where_supported(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-target-") as raw:
            root = Path(raw) / "repo"
            outside = Path(raw) / "outside.txt"
            root.mkdir()
            outside.write_bytes(b"outside\n")
            self.make_repo(root)
            (root / "target.txt").unlink()
            self.symlink_or_skip(outside, root / "target.txt", directory=False)
            with self.assertRaises(ProcessorError):
                snapshot_tracked_files(root, ("target.txt",))
            self.assertEqual(outside.read_bytes(), b"outside\n")

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point behavior")
    def test_windows_reparse_point_is_rejected_where_supported(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-reparse-") as raw:
            root = Path(raw) / "repo"
            outside = Path(raw) / "outside"
            root.mkdir()
            outside.mkdir()
            self.make_repo(root)
            redirect = root / "redirect"
            self.symlink_or_skip(outside, redirect, directory=True)
            metadata = os.lstat(redirect)
            self.assertTrue(
                getattr(metadata, "st_file_attributes", 0) & 0x400
            )
            with self.assertRaises(ProcessorError):
                RepositoryPathGuard(root).path("redirect/file.txt")

    def test_capability_unavailable_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="ledger-path-capability-") as raw:
            root = Path(raw)
            self.make_repo(root)

            def unavailable(_path):
                raise ProcessorError("processor_path_unsafe")

            with self.assertRaises(ProcessorError):
                RepositoryPathGuard(root, redirect_checker=unavailable)

    def test_startup_recovery_refuses_redirected_target_where_supported(self):
        class SimulatedProcessExit(BaseException):
            pass

        with tempfile.TemporaryDirectory(prefix="ledger-path-recovery-") as raw:
            root = Path(raw) / "repo"
            outside = Path(raw) / "outside.txt"
            root.mkdir()
            outside.write_bytes(b"outside\n")
            self.make_repo(root)

            def interrupt(stage, relative):
                if stage == "after_candidate_replace" and relative == "target.txt":
                    raise SimulatedProcessExit()

            with self.assertRaises(SimulatedProcessExit):
                replace_tracked_files(
                    root,
                    {"target.txt": b"candidate\n"},
                    failure_hook=interrupt,
                )
            (root / "target.txt").unlink()
            self.symlink_or_skip(outside, root / "target.txt", directory=False)
            with self.assertRaises(ProcessorError):
                recover_incomplete_transaction(root)
            self.assertEqual(outside.read_bytes(), b"outside\n")


if __name__ == "__main__":
    unittest.main()
