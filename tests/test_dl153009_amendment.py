from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.processor import cleanup_workflow
from scripts.processor.common import (
    FROZEN_BATCH_ID,
    ProcessorError,
    canonical_json_line_bytes,
    git_tree_file_bindings,
    git_tree_manifest_sha256,
    sha256_bytes,
)
from scripts.validate_receipts import (
    CANONICAL_PATHS,
    ReceiptValidationError,
    _load_schema,
    _parse_batch,
    _validate_terminal_seal_scope,
    main as validate_receipts_main,
    validate_all_tracked_batch_receipts,
    validate_batch_receipt_object,
    validate_source_replay,
)


ROOT = Path(__file__).resolve().parents[1]
STARTING_HEAD = "cb806ef022b4f776e3c67f834163a0c428377ec8"
ZERO_SHA = "0" * 40


def git(root: Path, *args: str, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("ascii").strip()


class WorkflowAuthorityFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dl153009-authority-")
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "core.autocrlf", "false")
        git(self.root, "config", "user.name", "public-fixture")
        git(self.root, "config", "user.email", "fixture" + "@" + "example.invalid")
        (self.root / "authority.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "authority.txt")
        git(self.root, "commit", "-qm", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "authority.txt").write_text("head\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "head")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.synthetic = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", "HEAD^{tree}"),
            "-p",
            self.head,
            "-m",
            "synthetic merge authority",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def resolve(self, event: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        values = {
            "github_sha": self.head,
            "checkout_sha": self.head,
            "pr_head_sha": "",
            "pr_base_sha": "",
            "before_sha": self.base,
            "dispatch_base_sha": "",
        }
        values.update(overrides)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "resolve_workflow_authority.py"),
            "--repository-root",
            str(self.root),
            "--event-name",
            event,
        ]
        for key, value in values.items():
            command.extend(["--" + key.replace("_", "-"), value])
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def assert_resolution(self, result: subprocess.CompletedProcess[str], head: str, base: str) -> None:
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertEqual({"head_sha": head, "base_sha": base}, json.loads(result.stdout))


class TestA1A2WorkflowAuthority(WorkflowAuthorityFixture):
    def test_production_workflows_bind_checkout_and_commands_to_resolver_outputs(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", workflow)
                self.assertIn("fetch-depth: 0", workflow)
                self.assertIn("id: authority", workflow)
                self.assertIn("scripts/resolve_workflow_authority.py", workflow)
                self.assertIn("steps.authority.outputs.base_sha", workflow)
                self.assertLess(
                    workflow.index("scripts/resolve_workflow_authority.py"),
                    workflow.index("python -m unittest"),
                )
                checkout_ref = "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
                checkout_uses_start = workflow.index("uses: actions/checkout@v4")
                checkout_start = workflow.rfind("- name:", 0, checkout_uses_start)
                checkout_end = workflow.find("\n      - name:", checkout_start + 1)
                if checkout_end == -1:
                    checkout_end = len(workflow)
                checkout_step = workflow[checkout_start:checkout_end]
                self.assertEqual(1, checkout_step.count(checkout_ref))
                self.assertNotIn("refs/pull/", checkout_step)

                authority_label = "- name: Verify immutable checkout and base authority"
                authority_start = workflow.index(authority_label)
                authority_end = workflow.find("\n      - name:", authority_start + 1)
                if authority_end == -1:
                    authority_end = len(workflow)
                authority_step = workflow[authority_start:authority_end]
                self.assertLess(checkout_start, authority_start)
                self.assertLess(authority_start, workflow.index("python -m unittest"))
                self.assertIn("id: authority", authority_step)
                self.assertIn("scripts/resolve_workflow_authority.py", authority_step)
                self.assertIn("--checkout-sha", authority_step)
                self.assertIn("--pr-head-sha", authority_step)
                self.assertIn("--pr-base-sha", authority_step)
                self.assertIn("--dispatch-base-sha", authority_step)
                self.assertIn("--output-file", authority_step)
                self.assertNotIn("refs/pull/", authority_step)
                self.assertNotIn("HISTORICAL_AUTHORITY_REF", workflow)
                for wildcard in ("refs/pull/*", "+refs/pull/*", "refs/pull/**/*"):
                    self.assertNotIn(wildcard, workflow)
                for forbidden in (
                    "git branch",
                    "git checkout",
                    "git push",
                    "git switch",
                    "refs/heads/",
                    "set +e",
                    "|| true",
                    "|| :",
                ):
                    self.assertNotIn(forbidden, authority_step)
                self.assertNotIn("continue-on-error", workflow)

    def test_pull_request_uses_literal_head_not_synthetic_merge(self):
        result = self.resolve(
            "pull_request",
            github_sha=self.synthetic,
            checkout_sha=self.head,
            pr_head_sha=self.head,
            pr_base_sha=self.base,
            before_sha="",
        )
        self.assert_resolution(result, self.head, self.base)
        self.assertNotEqual(self.synthetic, json.loads(result.stdout)["head_sha"])

    def test_push_uses_github_sha_and_nonzero_before(self):
        self.assert_resolution(self.resolve("push"), self.head, self.base)

    def test_zero_before_push_derives_exact_single_parent(self):
        self.assert_resolution(
            self.resolve("push", before_sha=ZERO_SHA),
            self.head,
            self.base,
        )

    def test_workflow_dispatch_requires_explicit_immutable_base(self):
        self.assert_resolution(
            self.resolve("workflow_dispatch", dispatch_base_sha=self.base, before_sha=""),
            self.head,
            self.base,
        )
        for invalid in ("", "main", "A" * 40, "a" * 39):
            with self.subTest(invalid=invalid):
                self.assertNotEqual(
                    0,
                    self.resolve(
                        "workflow_dispatch",
                        dispatch_base_sha=invalid,
                        before_sha="",
                    ).returncode,
                )

    def test_missing_malformed_or_contradictory_head_fails_closed(self):
        cases = (
            {"checkout_sha": ""},
            {"checkout_sha": "A" * 40},
            {"checkout_sha": self.base},
            {"github_sha": self.base},
            {"pr_head_sha": self.base, "pr_base_sha": self.base, "github_sha": self.synthetic},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                defaults = {
                    "github_sha": self.synthetic,
                    "checkout_sha": self.head,
                    "pr_head_sha": self.head,
                    "pr_base_sha": self.base,
                    "before_sha": "",
                }
                defaults.update(overrides)
                self.assertNotEqual(0, self.resolve("pull_request", **defaults).returncode)

    def test_unresolvable_and_nonancestor_authority_fails_closed(self):
        (self.root / "side.txt").write_text("side\n", encoding="utf-8")
        side_tree = git(self.root, "write-tree")
        unrelated = git(self.root, "commit-tree", side_tree, "-m", "unrelated")
        for overrides in (
            {"pr_base_sha": "f" * 40},
            {"pr_base_sha": unrelated},
            {"pr_head_sha": "e" * 40, "checkout_sha": "e" * 40},
        ):
            with self.subTest(overrides=overrides):
                defaults = {
                    "github_sha": self.synthetic,
                    "checkout_sha": self.head,
                    "pr_head_sha": self.head,
                    "pr_base_sha": self.base,
                    "before_sha": "",
                }
                defaults.update(overrides)
                self.assertNotEqual(0, self.resolve("pull_request", **defaults).returncode)

    def test_zero_before_root_and_merge_commit_fail_closed(self):
        root_commit = self.base
        self.assertNotEqual(
            0,
            self.resolve(
                "push",
                github_sha=root_commit,
                checkout_sha=root_commit,
                before_sha=ZERO_SHA,
            ).returncode,
        )
        merge = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", "HEAD^{tree}"),
            "-p",
            self.head,
            "-p",
            self.base,
            "-m",
            "ambiguous merge",
        )
        self.assertNotEqual(
            0,
            self.resolve(
                "push",
                github_sha=merge,
                checkout_sha=merge,
                before_sha=ZERO_SHA,
            ).returncode,
        )

    def test_post_checkout_verification_rejects_unexpected_head(self):
        git(self.root, "checkout", "-q", self.base)
        self.assertNotEqual(0, self.resolve("push").returncode)


class ReceiptHistoryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dl153009-receipts-")
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "core.autocrlf", "false")
        git(self.root, "config", "user.name", "public-fixture")
        git(self.root, "config", "user.email", "fixture" + "@" + "example.invalid")
        (self.root / "schema").mkdir()
        shutil.copy2(ROOT / "schema" / "receipt.schema.json", self.root / "schema" / "receipt.schema.json")
        git(self.root, "add", "schema/receipt.schema.json")
        git(self.root, "commit", "-qm", "canonical main base")
        self.initial_base = git(self.root, "rev-parse", "HEAD")
        self.records: list[dict[str, object]] = []
        self.bases: list[str] = []
        self.seals: list[str] = []
        self.pr_seals: list[str] = []
        self.candidates: list[str] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def canonical_files(self) -> dict[str, bytes]:
        evaluations = b"".join(canonical_json_line_bytes(item) for item in self.records)
        return {
            "evaluations.jsonl": evaluations,
            "ledger/dispositions.jsonl": b"",
            "README.md": ("# fixture\n\n" + "\n".join(str(item["run_id"]) for item in self.records) + "\n").encode(),
            "scorecard.md": ("# fixture scorecard\n" + str(len(self.records)) + "\n").encode(),
            "analysis/model-recommendation.json": (json.dumps({"count": len(self.records)}, sort_keys=True, indent=2) + "\n").encode(),
        }

    def append_batch(self, number: int, *, extra_seal_file: bool = False, path_batch_id: str | None = None, frozen: bool = False) -> tuple[str, str, str]:
        record = {
            "run_id": f"run-receipt-{number}",
            "provider": "OpenAI",
            "model": "GPT-5.6 Sol",
            "outcome": "accepted",
            "weighted_score_5": 4.5,
        }
        self.records.append(record)
        base_sha = self.seals[-1] if self.seals else self.initial_base
        contents = self.canonical_files()
        for relative, content in contents.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", f"candidate {number}")
        candidate = git(self.root, "rev-parse", "HEAD")
        record_line = canonical_json_line_bytes(record)
        digest = sha256_bytes(f"source-{number}".encode())
        batch_id = FROZEN_BATCH_ID if frozen else f"batch-fixture-{number}"
        receipt = {
            "schema_version": 2,
            "receipt_type": "batch",
            "batch_id": batch_id,
            "batch_mode": "initial" if number == 1 else "incremental",
            "controller_run_id": f"controller-fixture-{number}",
            "base_sha": base_sha,
            "canonical_main_sha": base_sha,
            "candidate_content_commit_sha": candidate,
            "pr_number": 151,
            "source_issue_number": 142,
            "receipt_issue_number": 143,
            "source_comment_watermark": number,
            "full_queue_count": 1,
            "latest_observed_comment_id": number,
            "latest_observed_update_time": f"2026-08-05T00:00:0{number}Z",
            "queue_snapshot_sha256": digest,
            "source_comment_ids": [number],
            "source_body_sha256": {str(number): digest},
            "selected_comment_ids": [number],
            "selected_comment_count": 1,
            "terminal_outcome_count": 1,
            "terminal_outcomes": {str(number): {"outcome_code": "admitted", "evaluation_run_id": record["run_id"], "canonical_record_sha256": sha256_bytes(record_line), "cleanup_eligible": False}},
            "admitted_run_ids": [record["run_id"]],
            "accepted_record_proofs": {record["run_id"]: {"provider": record["provider"], "model": record["model"], "outcome": record["outcome"], "weighted_score_5": record["weighted_score_5"]}},
            "canonical_record_hashes": {record["run_id"]: sha256_bytes(record_line)},
            "canonical_hashes": {name: sha256_bytes(contents[path]) for name, path in CANONICAL_PATHS.items()},
            "comment_bindings": [{"comment_id": number, "created_at": f"2026-08-05T00:00:0{number}Z", "updated_at": f"2026-08-05T00:00:0{number}Z", "body_sha256": digest, "outcome_code": "admitted", "evaluation_run_id": record["run_id"], "canonical_record_sha256": sha256_bytes(record_line), "cleanup_eligible": False}],
        }
        if not frozen:
            receipt["source_replay"] = {"adapter": "github-intake-v1"}
        path_id = path_batch_id or batch_id
        receipt_path = self.root / "ledger" / "receipts" / "batches" / f"{path_id}.json"
        receipt_relative = receipt_path.relative_to(self.root).as_posix()
        receipt["candidate_content_manifest"] = git_tree_file_bindings(
            self.root,
            candidate,
            excluded_paths=(receipt_relative,),
        )
        receipt["candidate_content_manifest_sha256"] = git_tree_manifest_sha256(
            receipt["candidate_content_manifest"]
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        if extra_seal_file:
            (self.root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", f"raw PR receipt-only seal {number}")
        pr_seal = git(self.root, "rev-parse", "HEAD")
        seal = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", f"{pr_seal}^{{tree}}"),
            "-p",
            base_sha,
            "-m",
            f"canonical squash-style seal {number}",
        )
        git(self.root, "checkout", "-q", seal)
        self.bases.append(base_sha)
        self.candidates.append(candidate)
        self.pr_seals.append(pr_seal)
        self.seals.append(seal)
        return receipt_path.relative_to(self.root).as_posix(), candidate, seal



class TestA3ImmutableMultiReceiptHistory(ReceiptHistoryFixture):
    def test_one_two_and_multiple_receipts_validate_historical_candidate_and_seal(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                self.tearDown()
                self.setUp()
                for number in range(1, count + 1):
                    self.append_batch(number)
                evidence = validate_all_tracked_batch_receipts(self.root, authority_sha=self.seals[-1], mode="canonical-main")
                self.assertEqual(count, evidence["receipt_count"])

    def test_incremental_receipt_records_previous_canonical_seal(self):
        self.append_batch(1)
        first_candidate = self.candidates[-1]
        first_seal = self.seals[-1]
        second_path, second_candidate, second_seal = self.append_batch(2)
        second = json.loads(
            subprocess.run(
                ["git", "show", f"HEAD:{second_path}"],
                cwd=self.root,
                capture_output=True,
                check=True,
            ).stdout
        )
        self.assertEqual(first_seal, second["base_sha"])
        self.assertEqual(first_seal, second["canonical_main_sha"])
        self.assertNotEqual(first_candidate, first_seal)
        self.assertEqual(
            second_candidate,
            git(self.root, "rev-parse", f"{self.pr_seals[-1]}^"),
        )
        self.assertEqual(
            first_seal,
            git(self.root, "rev-parse", f"{second_seal}^"),
        )


    def test_pr_mode_detects_only_current_terminal_receipt(self):
        self.append_batch(1, frozen=True)
        second_path, second_candidate, _second_seal = self.append_batch(2)
        second_pr_seal = self.pr_seals[-1]
        evidence = validate_all_tracked_batch_receipts(self.root, authority_sha=second_pr_seal, mode="pr")
        self.assertEqual(second_path, evidence["changed_receipt_path"])
        self.assertEqual(second_candidate, evidence["final_parent_sha"])

    def test_pr_mode_uses_historical_topology_for_nonfrozen_incremental_receipts(self):
        self.append_batch(1, frozen=True)
        frozen_canonical_seal = self.seals[0]

        first_path, first_candidate, first_canonical_seal = self.append_batch(2)
        first_pr_seal = self.pr_seals[1]

        current_path, current_candidate, _current_canonical_seal = self.append_batch(3)
        current_pr_seal = self.pr_seals[2]

        self.assertEqual(first_path, "ledger/receipts/batches/batch-fixture-2.json")
        self.assertEqual(current_path, "ledger/receipts/batches/batch-fixture-3.json")
        self.assertEqual(frozen_canonical_seal, git(self.root, "rev-parse", f"{first_candidate}^"))
        self.assertEqual(first_candidate, git(self.root, "rev-parse", f"{first_pr_seal}^"))
        self.assertEqual(frozen_canonical_seal, git(self.root, "rev-parse", f"{first_canonical_seal}^"))
        self.assertEqual(
            git(self.root, "rev-parse", f"{first_pr_seal}^{{tree}}"),
            git(self.root, "rev-parse", f"{first_canonical_seal}^{{tree}}"),
        )
        self.assertEqual(first_canonical_seal, git(self.root, "rev-parse", f"{current_candidate}^"))
        self.assertEqual(current_candidate, git(self.root, "rev-parse", f"{current_pr_seal}^"))

        evidence = validate_all_tracked_batch_receipts(
            self.root,
            authority_sha=current_pr_seal,
            mode="pr",
        )
        self.assertEqual(current_path, evidence["changed_receipt_path"])
        self.assertEqual(current_candidate, evidence["final_parent_sha"])

    def test_pr_mode_validates_historical_initial_canonical_seal(self):
        self.append_batch(1)
        current_path, current_candidate, _current_seal = self.append_batch(2)
        evidence = validate_all_tracked_batch_receipts(
            self.root,
            authority_sha=self.pr_seals[-1],
            mode="pr",
        )
        self.assertEqual(current_path, evidence["changed_receipt_path"])
        self.assertEqual(current_candidate, evidence["final_parent_sha"])

    def test_pr_mode_validates_multiple_historical_canonical_incremental_seals(self):
        self.append_batch(1, frozen=True)
        self.append_batch(2)
        self.append_batch(3)
        current_path, current_candidate, _current_seal = self.append_batch(4)
        evidence = validate_all_tracked_batch_receipts(
            self.root,
            authority_sha=self.pr_seals[-1],
            mode="pr",
        )
        self.assertEqual(4, evidence["receipt_count"])
        self.assertEqual(current_path, evidence["changed_receipt_path"])
        self.assertEqual(current_candidate, evidence["final_parent_sha"])

    def test_pr_mode_rejects_current_raw_seal_with_noncandidate_parent(self):
        self.append_batch(1, frozen=True)
        _current_path, current_candidate, _current_seal = self.append_batch(2)
        current_pr_seal = self.pr_seals[-1]
        wrong_candidate = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", f"{current_candidate}^{{tree}}"),
            "-p",
            self.seals[0],
            "-m",
            "wrong candidate identity",
        )
        wrong_pr_seal = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", f"{current_pr_seal}^{{tree}}"),
            "-p",
            wrong_candidate,
            "-m",
            "wrong raw PR parent",
        )
        with self.assertRaisesRegex(
            ReceiptValidationError,
            "^receipt_candidate_parent_mismatch$",
        ):
            validate_all_tracked_batch_receipts(
                self.root,
                authority_sha=wrong_pr_seal,
                mode="pr",
            )

    def test_historical_receipt_bytes_and_hashes_are_not_compared_to_later_canonical_bytes(self):
        first_path, _candidate, first_seal = self.append_batch(1)
        original = subprocess.run(["git", "show", f"{first_seal}:{first_path}"], cwd=self.root, capture_output=True, check=True).stdout
        self.append_batch(2)
        evidence = validate_all_tracked_batch_receipts(self.root, authority_sha=self.seals[-1], mode="canonical-main")
        self.assertEqual(2, evidence["receipt_count"])
        self.assertEqual(original, subprocess.run(["git", "show", f"HEAD:{first_path}"], cwd=self.root, capture_output=True, check=True).stdout)

    def test_duplicate_batch_ids_and_path_identity_conflicts_fail_closed(self):
        self.append_batch(1)
        with self.subTest("path_mismatch"):
            self.append_batch(2, path_batch_id="wrong-path")
            with self.assertRaises(ReceiptValidationError):
                validate_all_tracked_batch_receipts(self.root, authority_sha=self.seals[-1], mode="canonical-main")

    def test_seal_changing_unrelated_file_fails_closed(self):
        self.append_batch(1, extra_seal_file=True)
        with self.assertRaises(ReceiptValidationError):
            validate_all_tracked_batch_receipts(self.root, authority_sha=self.seals[-1], mode="canonical-main")

    def test_historical_receipt_mutation_and_candidate_tampering_fail_closed(self):
        path, _candidate, _seal = self.append_batch(1)
        self.append_batch(2)
        receipt_file = self.root / path
        value = json.loads(receipt_file.read_text(encoding="utf-8"))
        value["candidate_content_commit_sha"] = self.candidates[-1]
        receipt_file.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        git(self.root, "add", path)
        git(self.root, "commit", "-qm", "mutate historical receipt")
        with self.assertRaises(ReceiptValidationError):
            validate_all_tracked_batch_receipts(self.root, authority_sha=git(self.root, "rev-parse", "HEAD"), mode="canonical-main")

    def test_pr_mode_rejects_missing_or_multiple_terminal_receipts(self):
        self.append_batch(1)
        (self.root / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
        git(self.root, "add", "ordinary.txt")
        git(self.root, "commit", "-qm", "not a seal")
        with self.assertRaises(ReceiptValidationError):
            validate_all_tracked_batch_receipts(self.root, authority_sha=git(self.root, "rev-parse", "HEAD"), mode="pr")


class TestA3ReceiptReplayAndTampering(ReceiptHistoryFixture):
    def receipt_value(self, path: str, revision: str = "HEAD") -> dict[str, object]:
        raw = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=self.root,
            capture_output=True,
            check=True,
        ).stdout
        return json.loads(raw)

    def test_every_nonfrozen_receipt_dispatches_to_production_adapter(self):
        self.append_batch(1)
        self.append_batch(2)
        with mock.patch(
            "scripts.validate_receipts._validate_github_intake_source_replay",
            return_value={"outcomes": 1, "admissions": 1, "later_comments": 0},
        ) as replay:
            evidence = validate_source_replay(
                self.root,
                authority_sha=self.seals[-1],
                mode="canonical-main",
            )
        self.assertEqual(2, replay.call_count)
        self.assertEqual(2, evidence["replayed_outcome_count"])
        self.assertEqual(
            ["github-intake-v1", "github-intake-v1"],
            [item["adapter"] for item in evidence["replayed_receipts"]],
        )

    def test_actual_validate_receipts_main_runs_source_replay_mode(self):
        self.append_batch(1)
        with mock.patch(
            "scripts.validate_receipts._validate_github_intake_source_replay",
            return_value={"outcomes": 1, "admissions": 1, "later_comments": 0},
        ):
            result = validate_receipts_main(
                [
                    "--repository-root",
                    str(self.root),
                    "--mode",
                    "pr",
                    "--authority-sha",
                    self.pr_seals[-1],
                    "--validation-level",
                    "source-replay",
                ]
            )
        self.assertEqual(0, result)

    def test_frozen_receipt_routes_only_to_frozen_replay(self):
        _path, candidate, _seal = self.append_batch(1, frozen=True)
        seal = self.pr_seals[-1]
        with mock.patch(
            "scripts.validate_receipts._validate_frozen_source_replay",
            return_value={"outcomes": 101, "admissions": 0, "later_comments": 0},
        ) as frozen, mock.patch(
            "scripts.validate_receipts._validate_github_intake_source_replay"
        ) as incremental, mock.patch(
            "scripts.validate_receipts._validate_terminal_seal_scope",
            wraps=_validate_terminal_seal_scope,
        ) as terminal:
            evidence = validate_source_replay(
                self.root,
                authority_sha=seal,
                mode="pr",
                canonical_base_sha=self.bases[-1],
            )
        frozen.assert_called_once()
        incremental.assert_not_called()
        terminal.assert_called_once()
        self.assertEqual("pr", terminal.call_args.kwargs["mode"])
        self.assertEqual(candidate, terminal.call_args.kwargs["candidate_sha"])
        self.assertEqual(seal, terminal.call_args.kwargs["seal_sha"])
        self.assertEqual("frozen-v1", evidence["replayed_receipts"][0]["adapter"])

    def test_missing_unsupported_and_cross_routed_contracts_fail_closed(self):
        path, _candidate, _seal = self.append_batch(1)
        schema = _load_schema(self.root)
        receipt = self.receipt_value(path)
        variants = []
        missing = copy.deepcopy(receipt)
        missing.pop("source_replay")
        variants.append(missing)
        unsupported = copy.deepcopy(receipt)
        unsupported["source_replay"] = {"adapter": "unsupported"}
        variants.append(unsupported)
        cross_routed = copy.deepcopy(receipt)
        cross_routed["batch_id"] = "batch-20260729-gate3-amendment-004"
        variants.append(cross_routed)
        for value in variants:
            with self.subTest(batch_id=value["batch_id"]), self.assertRaises(ReceiptValidationError):
                _parse_batch(
                    (json.dumps(value, sort_keys=True, indent=2) + "\n").encode(),
                    schema,
                )

    def test_source_replay_mismatch_blocks_complete_validation(self):
        self.append_batch(1)
        with mock.patch(
            "scripts.validate_receipts._validate_github_intake_source_replay",
            side_effect=ReceiptValidationError("receipt_source_replay_mismatch"),
        ), self.assertRaises(ReceiptValidationError):
            validate_source_replay(
                self.root,
                authority_sha=self.pr_seals[-1],
                mode="pr",
            )

    def test_aggregate_record_hash_and_record_proof_tampering_fail_closed(self):
        path, _candidate, seal = self.append_batch(1)
        receipt = self.receipt_value(path, seal)
        mutations = []
        aggregate = copy.deepcopy(receipt)
        aggregate["canonical_hashes"]["evaluations_jsonl"] = "0" * 64
        mutations.append(aggregate)
        record_hash = copy.deepcopy(receipt)
        record_hash["canonical_record_hashes"]["run-receipt-1"] = "0" * 64
        mutations.append(record_hash)
        proof = copy.deepcopy(receipt)
        proof["accepted_record_proofs"]["run-receipt-1"]["weighted_score_5"] = 0
        mutations.append(proof)
        for value in mutations:
            with self.subTest(kind=len(mutations)), self.assertRaises(ReceiptValidationError):
                validate_batch_receipt_object(
                    self.root,
                    value,
                    authority_sha=seal,
                )

    def test_multiple_parent_seal_is_rejected(self):
        path, candidate, seal = self.append_batch(1)
        unrelated = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", f"{candidate}^{{tree}}"),
            "-m",
            "unrelated",
        )
        merge_seal = git(
            self.root,
            "commit-tree",
            git(self.root, "rev-parse", f"{seal}^{{tree}}"),
            "-p",
            candidate,
            "-p",
            unrelated,
            "-m",
            "invalid merge seal",
        )
        with self.assertRaises(ReceiptValidationError):
            _validate_terminal_seal_scope(
                self.root,
                seal_sha=merge_seal,
                receipt_path=path,
                candidate_sha=candidate,
            )

    def test_terminal_commit_changing_multiple_receipts_is_rejected(self):
        first_path, _candidate, _seal = self.append_batch(1)
        second_path, _candidate, _seal = self.append_batch(2)
        for path in (first_path, second_path):
            value = json.loads((self.root / path).read_text(encoding="utf-8"))
            value["candidate_content_commit_sha"] = git(self.root, "rev-parse", "HEAD")
            (self.root / path).write_text(
                json.dumps(value, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        git(self.root, "add", first_path, second_path)
        git(self.root, "commit", "-qm", "invalid dual seal")
        with self.assertRaises(ReceiptValidationError):
            validate_all_tracked_batch_receipts(
                self.root,
                authority_sha=git(self.root, "rev-parse", "HEAD"),
                mode="pr",
            )


class TestA4StableReviewThreadIdentity(unittest.TestCase):
    @staticmethod
    def config() -> cleanup_workflow.CleanupConfig:
        return cleanup_workflow.CleanupConfig(
            batch_id="batch-fixture",
            expected_head_sha="a" * 40,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="reviewed",
            canonical_merge_sha="b" * 40,
            canonical_main_sha="b" * 40,
            pr_state="closed",
            merge_state="merged",
            checks_state="passed",
            review_state="clear",
            recorded_receipt_status="absent",
            repository_root=ROOT,
        )

    @staticmethod
    def envelope(nodes: object, *, total: object, has_next: object = False, end_cursor: object = None) -> dict:
        return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes, "totalCount": total, "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor}}}}}}

    def threads(self, *responses: object) -> list[dict[str, object]]:
        with mock.patch.object(cleanup_workflow, "gh_json", side_effect=responses):
            return cleanup_workflow._gh_get_threads(self.config())

    @staticmethod
    def node(identity: object = "thread-1", resolved: object = True, outdated: object = False, **extra: object) -> dict[str, object]:
        return {"id": identity, "isResolved": resolved, "isOutdated": outdated, **extra}

    def test_query_requests_stable_id_and_exact_node_shape(self):
        captured: list[list[str]] = []
        def fake(_root, args, **_kwargs):
            captured.append(args)
            return self.envelope([], total=0)
        with mock.patch.object(cleanup_workflow, "gh_json", side_effect=fake):
            self.assertEqual([], cleanup_workflow._gh_get_threads(self.config()))
        query_arg = next(item for item in captured[0] if item.startswith("query="))
        self.assertIn("nodes{id,isResolved,isOutdated}", query_arg)

    def test_valid_empty_single_multiple_and_unique_pages(self):
        self.assertEqual([], self.threads(self.envelope([], total=0)))
        one = self.node()
        self.assertEqual([one], self.threads(self.envelope([one], total=1)))
        two = self.node("thread-2", False, True)
        self.assertEqual([one, two], self.threads(self.envelope([one, two], total=2)))
        self.assertEqual([one, two], self.threads(self.envelope([one], total=2, has_next=True, end_cursor="cursor-1"), self.envelope([two], total=2)))

    def test_duplicate_id_within_or_across_pages_fails_closed(self):
        duplicate = self.node("duplicate")
        cases = (
            (self.envelope([duplicate, copy.deepcopy(duplicate)], total=2),),
            (self.envelope([duplicate], total=2, has_next=True, end_cursor="cursor-1"), self.envelope([copy.deepcopy(duplicate)], total=2)),
        )
        for responses in cases:
            with self.subTest(pages=len(responses)), self.assertRaises(ProcessorError):
                self.threads(*responses)

    def test_duplicate_resolved_node_cannot_mask_unresolved_thread(self):
        duplicate = self.node("resolved", True, False)
        with self.assertRaises(ProcessorError):
            self.threads(self.envelope([duplicate, copy.deepcopy(duplicate)], total=2))

    def test_malformed_id_resolution_types_and_unexpected_fields_fail_closed(self):
        invalid_nodes = (
            {"isResolved": True, "isOutdated": False},
            self.node(None),
            self.node(""),
            self.node(1),
            self.node("x" * 257),
            self.node("bad\nidentity"),
            self.node("bad\u0085identity"),
            self.node(" whitespace "),
            self.node(resolved=None),
            self.node(resolved=1),
            self.node(outdated="false"),
            self.node(extra=True),
        )
        for node in invalid_nodes:
            with self.subTest(node_type=type(node.get("id")).__name__), self.assertRaises(ProcessorError):
                self.threads(self.envelope([node], total=1))

    def test_unique_count_below_above_changing_total_repeated_cursor_and_errors_block(self):
        error = self.envelope([], total=0)
        error["errors"] = [{"message": "redacted"}]
        cases = (
            (self.envelope([self.node()], total=2),),
            (self.envelope([self.node(), self.node("thread-2")], total=1),),
            (self.envelope([self.node()], total=2, has_next=True, end_cursor="cursor-1"), self.envelope([self.node("thread-2")], total=3)),
            (self.envelope([], total=2, has_next=True, end_cursor="cursor-1"), self.envelope([], total=2, has_next=True, end_cursor="cursor-1")),
            (error,),
        )
        for responses in cases:
            with self.subTest(pages=len(responses)), self.assertRaises(ProcessorError):
                self.threads(*responses)


if __name__ == "__main__":
    unittest.main()
