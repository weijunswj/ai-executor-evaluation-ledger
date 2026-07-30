import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.processor.cleanup_workflow import (
    CleanupConfig,
    _readback_live_authority,
    prepare_cleanup_receipt,
    publish_cleanup_receipt,
    run_cleanup,
)
from scripts.processor.common import ProcessorError, canonical_json_bytes, canonical_json_line_bytes, sha256_bytes
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
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes().replace(b"\r\n", b"\n"))
        body = "retained source fixture"
        digest = sha256_bytes(body.encode("utf-8"))
        queue_snapshot_digest = sha256_bytes(
            canonical_json_bytes(
                [{
                    "id": 1,
                    "created_at": "2026-07-29T10:00:00Z",
                    "updated_at": "2026-07-29T10:00:00Z",
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
        batch = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": batch_id,
            "batch_mode": "initial",
            "controller_run_id": "controller-cleanup-a005",
            "base_sha": "a" * 40,
            "canonical_main_sha": "a" * 40,
            "candidate_content_commit_sha": content_sha,
            "pr_number": 151,
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
        receipt_path.write_text(json.dumps(batch, sort_keys=True, indent=2) + "\n", encoding="utf-8")
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

    def test_cleanup_verifies_retention_and_stays_pending_without_receipt_proof(self):
        with tempfile.TemporaryDirectory(prefix="ledger-cleanup-test-") as raw:
            root = Path(raw)
            body, _ = self.fixture_cleanup_tree(root)

            def fetcher(comment_id, _root):
                return {
                    "id": comment_id,
                    "user": {"l" + "ogin": "fixture-author"},
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
                    "user": {"l" + "ogin": "fixture-author"},
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
            calls = []

            def publisher(body):
                calls.append(body)
                return 991

            def readback(locator):
                return {
                    "id": locator,
                    "body": calls[0],
                    "issue_url": "https://api.github.test/repos/example/ledger/issues/143",
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
            ):
                with self.assertRaises(ProcessorError, msg=unsafe):
                    guard.path(unsafe)

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
