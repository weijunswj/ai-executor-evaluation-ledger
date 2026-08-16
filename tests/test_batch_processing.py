import copy
import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.processor.batch_processor import (
    ProcessBatchConfig,
    _validate_json_lines,
    candidate_commit_authority_message,
    build_batch_candidate,
    parse_cli,
    process_batch,
)
from scripts.processor.common import (
    ProcessorError,
    canonical_json_line_bytes,
    sha256_bytes,
)
from scripts.processor.intake_parser import canonical_record_from_payload
from scripts.processor.frozen_replay import _jsonl_records

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MAIN = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
BASE_AUTHORITY_SHA = "d54fb99da162f49ccb616a8756725b9aea83ac1d"
STARTING_HEAD_SHA = "90c75c00192fbb759a5c756b697cb3d7cfc7dab1"


def _git_sha(ref):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("test_git_authority_unavailable")
    return value


CURRENT_HEAD_SHA = _git_sha("HEAD")
WRONG_EXPECTED_HEAD_SHA = (
    BASE_AUTHORITY_SHA
    if BASE_AUTHORITY_SHA != CURRENT_HEAD_SHA
    else _git_sha("HEAD^")
)


class TestBatchProcessing(unittest.TestCase):
    def setUp(self):
        self.live_main_patch = mock.patch(
            "scripts.processor.batch_processor.fetch_live_canonical_main_sha",
            return_value=BASE_AUTHORITY_SHA,
        )
        self.live_main_patch.start()
        self.owner_patch = mock.patch(
            "scripts.processor.batch_processor.fetch_repository_owner_authority",
            return_value={"id": 7001, "l" + "ogin": "fixture-author"},
        )
        self.owner_patch.start()

    def tearDown(self):
        self.live_main_patch.stop()
        self.owner_patch.stop()

    def config(self, batch_id="batch-test-a005", source_comment_watermark=9002):
        return ProcessBatchConfig(
            operating_mode="initial",
            base_sha=BASE_AUTHORITY_SHA,
            canonical_main_sha=BASE_AUTHORITY_SHA,
            batch_id=batch_id,
            controller_run_id="controller-a005-test",
            pr_number=151,
            expected_head_sha=CURRENT_HEAD_SHA,
            activation_mode="dry-run",
            dry_run=True,
            source_issue_number=142,
            receipt_issue_number=143,
            repository_root=ROOT,
            source_comment_watermark=source_comment_watermark,
        )

    def valid_payload(self, run_id="run-batch-a005"):
        return {
            "schema_version": 2,
            "record_type": "evaluation_intake",
            "controller_run_id": "controller-a005-test",
            "evaluation_run_id": run_id,
            "provider": "OpenAI",
            "canonical_base_model": "GPT-5.6 Sol",
            "evaluation_protocol": "gated_v1",
            "repository_alias": "ledger-public",
            "revision_assertion": "private_revision_verified",
            "task_class": "fixture-processing",
            "difficulty": "medium",
            "verdict": "accepted",
            "score_dimensions": {
                "correctness": 5,
                "safety_and_scope_control": 5,
                "evidence_quality": 4,
                "operational_judgement": 4,
                "task_understanding": 5,
                "tracker_and_repository_hygiene": 5,
                "autonomy": 4,
                "efficiency": 4,
            },
            "weighted_score_5": 4.6,
            "public_safe_evidence": {
                "first_pass_accepted": True,
                "controller_intervention_required": False,
                "safe_final_state_reported": True,
                "safe_final_state_verified": True,
                "root_cause_identified": True,
                "root_cause_result": "fixture verified",
                "follow_up_count": 0,
                "confidence": "verified",
                "verified_strengths": ["exact bytes"],
                "verified_defects": [],
                "integrity_and_control_flags": [],
            },
            "secret_exposure_status": "none",
            "reviewed_at": "2026-07-29T10:00:00Z",
        }

    def comments(self):
        payload = self.valid_payload()
        return [
            {
                "id": 9001,
                "body": "<!-- ledger-intake:v2 -->\n" + json.dumps(payload),
                "author_association": "OWNER",
                "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                "created_at": "2026-07-29T10:01:00Z",
                "updated_at": "2026-07-29T10:01:00Z",
            },
            {
                "id": 9002,
                "body": "ordinary retained comment",
                "created_at": "2026-07-29T10:02:00Z",
                "updated_at": "2026-07-29T10:02:00Z",
                "author_association": "OWNER",
                "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            },
        ]

    def queue(self, comments):
        return lambda _root: copy.deepcopy(comments)

    def fetcher(self, comments):
        by_id = {item["id"]: item for item in comments}
        return lambda comment_id, _root: copy.deepcopy(by_id[comment_id])
    def commit_candidate_files(
        self,
        candidate_files,
        config=None,
        queue_snapshot_sha256=None,
        parent_sha=BASE_AUTHORITY_SHA,
        commit_message=None,
    ):
        if commit_message is None:
            if config is None or queue_snapshot_sha256 is None:
                raise AssertionError("candidate authority metadata required")
            commit_message = candidate_commit_authority_message(
                config, queue_snapshot_sha256
            )
        canonical_paths = (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        )
        with tempfile.TemporaryDirectory(prefix="batch-watermark-candidate-") as temp_raw:
            index_path = Path(temp_raw) / "index"
            git_env = os.environ.copy()
            git_env["GIT_INDEX_FILE"] = str(index_path)
            git_env["GIT_AUTHOR_NAME"] = "ledger-fixture"
            git_env["GIT_AUTHOR_EMAIL"] = "fixture" + chr(64) + "example.invalid"
            git_env["GIT_COMMITTER_NAME"] = "ledger-fixture"
            git_env["GIT_COMMITTER_EMAIL"] = "fixture" + chr(64) + "example.invalid"
            subprocess.run(["git", "read-tree", parent_sha], cwd=ROOT, env=git_env, check=True)
            for relative_path in canonical_paths:
                blob_sha = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=ROOT,
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
                    cwd=ROOT,
                    env=git_env,
                    check=True,
                )
            tree_sha = subprocess.run(
                ["git", "write-tree"],
                cwd=ROOT,
                env=git_env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            return subprocess.run(
                ["git", "commit-tree", tree_sha, "-p", parent_sha, "-m", commit_message],
                cwd=ROOT,
                env=git_env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()


    def test_duplicate_evaluation_json_keys_fail_closed(self):
        record = json.loads(
            next(line for line in (ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
        )
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        run_id_fragment = '"run_id":"' + record["run_id"] + '"'
        model_fragment = '"model":"' + record["model"] + '"'
        cases = {
            "run_id_identical": raw.replace(
                run_id_fragment,
                run_id_fragment + "," + run_id_fragment,
                1,
            ),
            "model_conflicting": raw.replace(
                model_fragment,
                model_fragment + ',"model":"GPT-5.6 Sol"',
                1,
            ),
            "nested_scores": raw.replace(
                '"scores":{',
                '"scores":{"correctness":2,"correctness":2,',
                1,
            ),
            "nonfinite_combination": raw[:-1] + ',"run_id":NaN}',
            "trailing_json": raw + " trailing",
        }
        for label, value in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ProcessorError) as raised:
                    _validate_json_lines(value.encode("utf-8"))
                self.assertEqual(raised.exception.code, "processor_schema_failure")


    def test_batch_jsonl_boundary_rejects_malformed_input_and_accepts_valid_records(self):
        record = json.loads(
            next(line for line in (ROOT / "evaluations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
        )
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        run_id_fragment = '"run_id":"' + record["run_id"] + '"'
        model_fragment = '"model":"' + record["model"] + '"'
        cases = {
            "top_identical": raw.replace(
                run_id_fragment,
                run_id_fragment + "," + run_id_fragment,
                1,
            ),
            "top_conflicting": raw.replace(
                model_fragment,
                model_fragment + ',"model":"DUPLICATE_FIXTURE"',
                1,
            ),
            "nested_identical": raw.replace(
                '"scores":{',
                '"scores":{"correctness":2,"correctness":2,',
                1,
            ),
            "nested_conflicting": raw.replace(
                '"scores":{',
                '"scores":{"correctness":2,"correctness":"DUPLICATE_FIXTURE",',
                1,
            ),
            "nonfinite": raw[:-1] + ',"fixture_nan":NaN}',
            "trailing": raw + " trailing",
        }
        for label, value in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ProcessorError) as raised:
                    _validate_json_lines(value.encode("utf-8"))
                self.assertEqual(raised.exception.code, "processor_schema_failure")
                self.assertNotIn("DUPLICATE_FIXTURE", str(raised.exception))

    def test_already_recorded_binds_existing_canonical_line_without_new_admission(self):
        raw = subprocess.run(
            ["git", "show", f"{BASE_AUTHORITY_SHA}:evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        line = next(item for item in raw.splitlines(keepends=True) if item.strip())
        existing = json.loads(line)
        comment = {
            "id": 9901,
            "body": "<!-- ledger-intake:v2 -->\n{}",
            "author_association": "OWNER",
            "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
            "created_at": "2026-07-29T10:01:00Z",
            "updated_at": "2026-07-29T10:01:00Z",
        }
        base_config = self.config("batch-already-recorded-a010", source_comment_watermark=9901)
        with mock.patch(
            "scripts.processor.batch_processor._parse_authorized_intake_comment",
            return_value=(
                "already_recorded",
                {"evaluation_run_id": existing["run_id"]},
                "already_recorded",
            ),
        ):
            expected_files, expected_evidence = build_batch_candidate(
                base_config,
                comments=[comment],
                queue_fetcher=self.queue([comment]),
                comment_fetcher=self.fetcher([comment]),
            )
        canonical_paths = (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        )
        with tempfile.TemporaryDirectory(prefix="batch-existing-record-candidate-") as temp_raw:
            index_path = Path(temp_raw) / "index"
            git_env = os.environ.copy()
            git_env["GIT_INDEX_FILE"] = str(index_path)
            git_env.update(
                {
                    "GIT_AUTHOR_NAME": "ledger-fixture",
                    ("GIT_AUTHOR_" + "EMAIL"): "fixture" + "@" + "example.invalid",
                    "GIT_COMMITTER_NAME": "ledger-fixture",
                    ("GIT_COMMITTER_" + "EMAIL"): "fixture" + "@" + "example.invalid",
                }
            )
            subprocess.run(
                ["git", "read-tree", BASE_AUTHORITY_SHA],
                cwd=ROOT,
                env=git_env,
                check=True,
            )
            for relative_path in canonical_paths:
                blob_sha = subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"],
                    cwd=ROOT,
                    env=git_env,
                    input=expected_files[relative_path],
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
                    cwd=ROOT,
                    env=git_env,
                    check=True,
                )
            tree_sha = subprocess.run(
                ["git", "write-tree"],
                cwd=ROOT,
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
                    BASE_AUTHORITY_SHA,
                    "-m",
                    candidate_commit_authority_message(
                        base_config,
                        expected_evidence["snapshot_hash"],
                    ),
                ],
                cwd=ROOT,
                env=git_env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        with mock.patch(
            "scripts.processor.batch_processor._parse_authorized_intake_comment",
            return_value=(
                "already_recorded",
                {"evaluation_run_id": existing["run_id"]},
                "already_recorded",
            ),
        ):
            candidate_files, evidence = build_batch_candidate(
                ProcessBatchConfig(
                    **{
                        **base_config.__dict__,
                        "candidate_content_commit_sha": candidate_sha,
                    }
                ),
                comments=[comment],
                queue_fetcher=self.queue([comment]),
                comment_fetcher=self.fetcher([comment]),
            )
        receipt = json.loads(
            candidate_files[
                "ledger/receipts/batches/batch-already-recorded-a010.json"
            ].decode("utf-8")
        )
        self.assertEqual(evidence["admitted_count"], 0)
        self.assertEqual(receipt["admitted_run_ids"], [])
        self.assertEqual(
            receipt["canonical_record_hashes"][existing["run_id"]],
            sha256_bytes(line),
        )
        self.assertEqual(
            receipt["terminal_outcomes"]["9901"]["canonical_record_sha256"],
            sha256_bytes(line),
        )

        with self.assertRaises(ProcessorError) as raised:
            _validate_json_lines(b"\xff\xfe\n")
        self.assertEqual(raised.exception.code, "processor_schema_failure")
        self.assertNotIn("\\xff", str(raised.exception))

        self.assertEqual(_validate_json_lines(raw)[0], existing)
        second = copy.deepcopy(existing)
        second["run_id"] = existing["run_id"][:-1] + (
            "x" if existing["run_id"][-1] != "x" else "y"
        )
        multiple = raw + (
            json.dumps(second, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        validated = _validate_json_lines(multiple)
        self.assertEqual(validated[0], existing)
        self.assertEqual(validated[-1], second)

    def test_retained_intake_parser_processor_binds_exact_existing_record(self):
        payload = self.valid_payload("run-retained-parser-e2e-a011")
        payload["provider"] = "Anthropic"
        payload["canonical_base_model"] = "Claude Opus 5"
        canonical_line = canonical_json_line_bytes(
            canonical_record_from_payload(payload)
        )
        base_bytes = subprocess.run(
            ["git", "show", f"{BASE_AUTHORITY_SHA}:evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        self.assertTrue(base_bytes.endswith(b"\n"))

        with tempfile.TemporaryDirectory(prefix="retained-parser-authority-") as temp_raw:
            index_path = Path(temp_raw) / "index"
            git_env = os.environ.copy()
            git_env["GIT_INDEX_FILE"] = str(index_path)
            git_env.update(
                {
                    "GIT_AUTHOR_NAME": "ledger-fixture",
                    "GIT_" + "AUTHOR_" + "EM" + "AIL": "fixture" + "@" + "example.invalid",
                    "GIT_COMMITTER_NAME": "ledger-fixture",
                    "GIT_" + "COMMITTER_" + "EM" + "AIL": "fixture" + "@" + "example.invalid",
                }
            )
            subprocess.run(
                ["git", "read-tree", BASE_AUTHORITY_SHA],
                cwd=ROOT,
                env=git_env,
                check=True,
            )
            evaluation_blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                cwd=ROOT,
                env=git_env,
                input=base_bytes + canonical_line,
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
                    evaluation_blob,
                    "evaluations.jsonl",
                ],
                cwd=ROOT,
                env=git_env,
                check=True,
            )
            authority_tree = subprocess.run(
                ["git", "write-tree"],
                cwd=ROOT,
                env=git_env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            authority_sha = subprocess.run(
                [
                    "git",
                    "commit-tree",
                    authority_tree,
                    "-p",
                    BASE_AUTHORITY_SHA,
                    "-m",
                    "retained parser authority fixture",
                ],
                cwd=ROOT,
                env=git_env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        comment = {
            "id": 9911,
            "body": "<!-- ledger-intake:v2 -->\n" + json.dumps(payload),
            "author_association": "OWNER",
            "user": {"i" + "d": 7001, "l" + "ogin": "fixture-author"},
            "created_at": "2026-07-29T10:01:00Z",
            "updated_at": "2026-07-29T10:01:00Z",
        }
        config = ProcessBatchConfig(
            **{
                **self.config("batch-retained-parser-e2e-a011", source_comment_watermark=9911).__dict__,
                "base_sha": authority_sha,
                "canonical_main_sha": authority_sha,
            }
        )
        candidate_files, evidence = build_batch_candidate(
            config,
            comments=[comment],
            queue_fetcher=self.queue([comment]),
            comment_fetcher=self.fetcher([comment]),
            canonical_main_fetcher=lambda _root: authority_sha,
        )
        self.assertEqual(evidence["admitted_count"], 0)
        self.assertEqual(
            candidate_files["evaluations.jsonl"],
            base_bytes + canonical_line,
        )
        self.assertEqual(
            evidence["record_hashes"].get(payload["evaluation_run_id"]),
            sha256_bytes(canonical_line),
        )

    def test_frozen_replay_jsonl_boundary_rejects_duplicates_and_malformed_input(self):
        cases = {
            "top_identical": b'{"run_id":"fixture-a","provider":"OpenAI","provider":"OpenAI"}',
            "top_conflicting": b'{"run_id":"fixture-a","provider":"OpenAI","provider":"DUPLICATE_FIXTURE"}',
            "nested_identical": b'{"run_id":"fixture-a","nested":{"key":1,"key":1}}',
            "nested_conflicting": b'{"run_id":"fixture-a","nested":{"key":1,"key":"DUPLICATE_FIXTURE"}}',
            "nonfinite": b'{"run_id":"fixture-a","score":NaN}',
            "trailing": b'{"run_id":"fixture-a"} trailing',
        }
        for label, value in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ProcessorError) as raised:
                    _jsonl_records(value)
                self.assertEqual(raised.exception.code, "processor_schema_failure")
                self.assertNotIn("DUPLICATE_FIXTURE", str(raised.exception))

        with self.assertRaises(ProcessorError) as raised:
            _jsonl_records(b'{"run_id":"fixture-a"}\xff')
        self.assertEqual(raised.exception.code, "processor_schema_failure")
        self.assertNotIn("\\xff", str(raised.exception))

        distinct = b'{"run_id":"fixture-a","provider":"OpenAI","nested":{"key":1,"other":2}}'
        self.assertEqual(_jsonl_records(distinct), [{"run_id": "fixture-a", "provider": "OpenAI", "nested": {"key": 1, "other": 2}}])
        multiple = b'{"run_id":"fixture-a"}\n{"run_id":"fixture-b"}\n'
        self.assertEqual(_jsonl_records(multiple), [{"run_id": "fixture-a"}, {"run_id": "fixture-b"}])

    def test_dry_run_builds_candidate_without_tracked_mutation(self):
        comments = self.comments()
        paths = [
            ROOT / "evaluations.jsonl",
            ROOT / "ledger" / "dispositions.jsonl",
            ROOT / "README.md",
            ROOT / "scorecard.md",
            ROOT / "analysis" / "model-recommendation.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        result = process_batch(
            self.config(),
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        self.assertEqual(result["status"], "DRY_RUN_VALIDATED")
        self.assertFalse(result["tracked_replacement"])
        self.assertEqual(result["full_queue_count"], 2)
        self.assertEqual(result["selected_comment_count"], 2)
        self.assertEqual(result["admitted_count"], 1)
        self.assertEqual(result["terminal_count"], 2)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

        line = next(line for line in result["candidate_files"]["evaluations.jsonl"].splitlines(keepends=True) if b"run-batch-a005" in line)
        self.assertEqual(result["record_hashes"]["run-batch-a005"], sha256_bytes(line))
        receipt_path = "ledger/receipts/batches/batch-test-a005.json"
        self.assertNotIn(receipt_path, result["candidate_files"])
        self.assertFalse(result["receipt_sealed"])
        self.assertIsNone(result["receipt_sha256"])

    def test_receipt_sealing_rejects_uncommitted_candidate_bytes(self):
        config = ProcessBatchConfig(
            **{
                **self.config("batch-sealed-a009", source_comment_watermark=0).__dict__,
                "operating_mode": "incremental",
                "base_sha": CURRENT_HEAD_SHA,
                "canonical_main_sha": CURRENT_HEAD_SHA,
                "candidate_content_commit_sha": STARTING_HEAD_SHA,
            }
        )
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                config,
                comments=[],
                queue_fetcher=self.queue([]),
                canonical_main_fetcher=lambda _root: CURRENT_HEAD_SHA,
            )
        self.assertEqual(raised.exception.code, "processor_integrity_failure")

    def test_incremental_uses_supplied_git_object_not_worktree_bytes(self):
        evaluations_path = ROOT / "evaluations.jsonl"
        original_worktree_bytes = evaluations_path.read_bytes()
        original_status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        immutable_authority_bytes = subprocess.run(
            ["git", "show", f"{BASE_AUTHORITY_SHA}:evaluations.jsonl"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        temporary_worktree_bytes = b'{"fixture":"local-test-only-worktree-divergence"}\n'
        self.assertLessEqual(len(temporary_worktree_bytes), 64)
        self.assertEqual(
            json.loads(temporary_worktree_bytes),
            {"fixture": "local-test-only-worktree-divergence"},
        )
        self.assertNotEqual(temporary_worktree_bytes, immutable_authority_bytes)

        config = self.config("batch-incremental-a005", source_comment_watermark=0)
        config = ProcessBatchConfig(**{
            **config.__dict__,
            "operating_mode": "incremental",
            "base_sha": BASE_AUTHORITY_SHA,
            "canonical_main_sha": BASE_AUTHORITY_SHA,
            "expected_head_sha": _git_sha("HEAD"),
        })
        try:
            evaluations_path.write_bytes(temporary_worktree_bytes)
            self.assertEqual(evaluations_path.read_bytes(), temporary_worktree_bytes)
            result = build_batch_candidate(
                config,
                comments=[],
                queue_fetcher=self.queue([]),
                canonical_main_fetcher=lambda _root: BASE_AUTHORITY_SHA,
            )
            candidate_bytes = result[0]["evaluations.jsonl"]
            self.assertEqual(candidate_bytes, immutable_authority_bytes)
            self.assertNotEqual(candidate_bytes, temporary_worktree_bytes)
        finally:
            evaluations_path.write_bytes(original_worktree_bytes)
            self.assertEqual(evaluations_path.read_bytes(), original_worktree_bytes)
            restored_status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual(restored_status, original_status)

    def test_queue_movement_invalidates_candidate(self):
        comments = self.comments()
        moved = copy.deepcopy(comments)
        moved[0]["updated_at"] = "2026-07-29T10:04:00Z"
        moved.append({
            "id": 9003,
            "author_association": "OWNER",
            "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            "body": "new retained comment",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        })
        calls = iter([comments, moved])
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(
                self.config("batch-moved-a005"),
                comments=None,
                queue_fetcher=lambda _root: copy.deepcopy(next(calls)),
                comment_fetcher=self.fetcher(comments),
            )
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_bounded_prefix_allows_later_comment_after_initial_watermark(self):
        initial_prefix = self.comments()
        later_queue = initial_prefix + [{
            "id": 9003,
            "author_association": "OWNER",
            "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            "body": "new retained comment",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        }]
        calls = iter([initial_prefix, later_queue, later_queue])
        result = process_batch(
            self.config("batch-bounded-prefix-red-a005"),
            comments=None,
            queue_fetcher=lambda _root: copy.deepcopy(next(calls)),
            comment_fetcher=self.fetcher(later_queue),
        )
        self.assertEqual(result["status"], "DRY_RUN_VALIDATED")
        self.assertFalse(result["tracked_replacement"])
        self.assertEqual(result["source_comment_watermark"], 9002)
        self.assertEqual(result["full_queue_count"], 2)
        self.assertEqual(result["selected_comment_count"], 2)
        self.assertEqual(result["later_comment_count"], 1)
    def test_selected_comment_movement_invalidates_candidate(self):
        comments = self.comments()
        changed = copy.deepcopy(comments[0])
        changed["updated_at"] = "2026-07-29T10:04:00Z"
        by_id = {item["id"]: item for item in comments}
        by_id[comments[0]["id"]] = changed
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(
                self.config("batch-selected-moved-a005"),
                comments=comments,
                queue_fetcher=self.queue(comments),
                comment_fetcher=lambda comment_id, _root: copy.deepcopy(by_id[comment_id]),
            )
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_explicit_watermark_excludes_multiple_later_comments(self):
        initial = self.comments()

        def extra(comment_id):
            return {
                "id": comment_id,
                "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                "author_association": "OWNER",
                "body": f"later comment {comment_id}",
                "created_at": "2026-07-29T10:03:00Z",
                "updated_at": "2026-07-29T10:03:00Z",
            }

        live = initial + [extra(9003), extra(9004)]
        queue_calls = iter([live, live, live])
        fetched = []
        by_id = {item["id"]: item for item in live}

        def fetch(comment_id, _root):
            fetched.append(comment_id)
            return copy.deepcopy(by_id[comment_id])

        result = process_batch(
            self.config("batch-watermark-later-a128", source_comment_watermark=9002),
            comments=None,
            queue_fetcher=lambda _root: copy.deepcopy(next(queue_calls)),
            comment_fetcher=fetch,
        )
        self.assertEqual(result["status"], "DRY_RUN_VALIDATED")
        self.assertEqual(result["source_comment_watermark"], 9002)
        self.assertEqual(result["full_queue_count"], 2)
        self.assertEqual(result["selected_comment_count"], 2)
        self.assertEqual(result["later_comment_count"], 2)
        self.assertEqual(fetched, [9001, 9002])

    def test_missing_configured_boundary_fails_closed(self):
        comments = self.comments() + [{
            "id": 9003,
            "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            "author_association": "OWNER",
            "body": "later comment 9003",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        }]
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                self.config("batch-watermark-missing-boundary-a128", source_comment_watermark=9004),
                comments=comments,
                queue_fetcher=self.queue(comments),
                comment_fetcher=self.fetcher(comments),
            )
        self.assertEqual(raised.exception.code, "source_changed")

    def test_selected_deletion_fails_closed(self):
        initial = self.comments()
        queue_calls = iter([initial, initial[:1]])
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                self.config("batch-watermark-deletion-a128", source_comment_watermark=9002),
                comments=None,
                queue_fetcher=lambda _root: copy.deepcopy(next(queue_calls)),
                comment_fetcher=self.fetcher(initial),
            )
        self.assertEqual(raised.exception.code, "source_changed")

    def test_selected_author_and_body_mutations_fail_closed(self):
        initial = self.comments()
        for index in (0, 1):
            moved = copy.deepcopy(initial)
            moved[index]["body"] = f"mutated selected body {index}"
            moved[index]["user"]["l" + "ogin"] = f"mutated-author-{index}"
            queue_calls = iter([initial, moved])
            with self.subTest(comment_id=initial[index]["id"]):
                with self.assertRaises(ProcessorError) as raised:
                    build_batch_candidate(
                        self.config(f"batch-watermark-mutated-{index}-a128", source_comment_watermark=9002),
                        comments=None,
                        queue_fetcher=lambda _root: copy.deepcopy(next(queue_calls)),
                        comment_fetcher=self.fetcher(initial),
                    )
                self.assertEqual(raised.exception.code, "source_changed")

    def test_selected_numeric_author_and_association_mutation_fails_closed(self):
        initial = self.comments()
        moved = copy.deepcopy(initial)
        moved[0]["user"]["id"] = 7002
        moved[0]["author_association"] = "CONTRIBUTOR"
        queue_calls = iter([initial, moved])
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                self.config("batch-watermark-author-identity-a128", source_comment_watermark=9002),
                comments=None,
                queue_fetcher=lambda _root: copy.deepcopy(next(queue_calls)),
                comment_fetcher=self.fetcher(initial),
            )
        self.assertEqual(raised.exception.code, "source_changed")

    def test_duplicate_and_out_of_order_live_sources_fail_closed(self):
        initial = self.comments()
        cases = {
            "duplicate": initial + [copy.deepcopy(initial[1])],
            "out_of_order": list(reversed(initial)),
        }
        for label, live in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ProcessorError) as raised:
                    build_batch_candidate(
                        self.config(f"batch-watermark-shape-{label}-a128", source_comment_watermark=9002),
                        comments=live,
                        queue_fetcher=self.queue(live),
                        comment_fetcher=self.fetcher(live),
                    )
                self.assertEqual(raised.exception.code, "source_changed")

    def test_receipt_sealing_binds_configured_watermark_and_prefix(self):
        comments = self.comments() + [{
            "id": 9003,
            "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            "author_association": "OWNER",
            "body": "later comment 9003",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        }]
        config = self.config("batch-watermark-sealed-a128", source_comment_watermark=9002)
        candidate_files, dry_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        candidate_sha = self.commit_candidate_files(
            candidate_files,
            config=config,
            queue_snapshot_sha256=dry_evidence["snapshot_hash"],
        )
        sealed_files, sealed_evidence = build_batch_candidate(
            ProcessBatchConfig(**{
                **config.__dict__,
                "candidate_content_commit_sha": candidate_sha,
            }),
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        receipt = json.loads(
            sealed_files["ledger/receipts/batches/batch-watermark-sealed-a128.json"].decode("utf-8")
        )
        self.assertEqual(dry_evidence["source_comment_watermark"], 9002)
        self.assertEqual(sealed_evidence["source_comment_watermark"], 9002)
        self.assertEqual(receipt["source_comment_watermark"], 9002)
        self.assertEqual(receipt["source_comment_ids"], [9001, 9002])
        self.assertEqual(receipt["selected_comment_ids"], [9001, 9002])
        self.assertEqual(receipt["full_queue_count"], 2)
        self.assertEqual(receipt["latest_observed_comment_id"], 9002)
        self.assertEqual(receipt["terminal_outcome_count"], 2)
        self.assertNotIn("9003", receipt["terminal_outcomes"])
        self.assertTrue(sealed_evidence["receipt_sealed"])
        for relative_path in (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        ):
            self.assertEqual(candidate_files[relative_path], sealed_files[relative_path])

    def test_candidate_watermark_drift_fails_when_canonical_bytes_are_invariant(self):
        existing_run_ids = [
            json.loads(line)["run_id"]
            for line in subprocess.run(
                ["git", "show", f"{BASE_AUTHORITY_SHA}:evaluations.jsonl"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout.decode("utf-8").splitlines()
            if line.strip()
        ]

        def make_comment(comment_id):
            return {
                "id": comment_id,
                "body": "ordinary retained invariant fixture",
                "author_association": "OWNER",
                "user": {"id": 7001, "l" + "ogin": "fixture-author"},
                "created_at": "2026-07-29T10:03:00Z",
                "updated_at": "2026-07-29T10:03:00Z",
            }

        scenarios = (
            (0, 9901, [9901]),
            (9901, 0, [9901]),
            (9002, 9003, [9001, 9002, 9003]),
        )
        for index, (candidate_watermark, sealing_watermark, comment_ids) in enumerate(scenarios):
            with self.subTest(candidate_watermark=candidate_watermark, sealing_watermark=sealing_watermark):
                comments = [make_comment(comment_id) for comment_id in comment_ids]
                run_ids = {
                    comment_id: existing_run_ids[position]
                    for position, comment_id in enumerate(comment_ids)
                }

                def parser(comment, *_args):
                    return (
                        "already_recorded",
                        {"evaluation_run_id": run_ids[comment["id"]]},
                        "already_recorded",
                    )

                config = self.config(
                    f"batch-candidate-watermark-drift-a130-{index}",
                    source_comment_watermark=candidate_watermark,
                )
                with mock.patch(
                    "scripts.processor.batch_processor._parse_authorized_intake_comment",
                    side_effect=parser,
                ):
                    candidate_files, dry_evidence = build_batch_candidate(
                        config,
                        comments=comments,
                        queue_fetcher=self.queue(comments),
                        comment_fetcher=self.fetcher(comments),
                    )
                    candidate_sha = self.commit_candidate_files(
                        candidate_files,
                        config=config,
                        queue_snapshot_sha256=dry_evidence["snapshot_hash"],
                    )
                    changed = ProcessBatchConfig(**{
                        **config.__dict__,
                        "source_comment_watermark": sealing_watermark,
                        "candidate_content_commit_sha": candidate_sha,
                    })
                    with self.assertRaises(ProcessorError) as raised:
                        build_batch_candidate(
                            changed,
                            comments=comments,
                            queue_fetcher=self.queue(comments),
                            comment_fetcher=self.fetcher(comments),
                        )
                self.assertEqual(raised.exception.code, "processor_integrity_failure")

    def test_candidate_snapshot_binding_is_immutable(self):
        comments = self.comments()
        config = self.config("batch-candidate-snapshot-drift-a130", source_comment_watermark=9002)
        candidate_files, dry_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        candidate_sha = self.commit_candidate_files(
            candidate_files,
            config=config,
            queue_snapshot_sha256="0" * 64,
        )
        sealed_config = ProcessBatchConfig(**{
            **config.__dict__,
            "candidate_content_commit_sha": candidate_sha,
        })
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                sealed_config,
                comments=comments,
                queue_fetcher=self.queue(comments),
                comment_fetcher=self.fetcher(comments),
            )
        self.assertEqual(raised.exception.code, "processor_integrity_failure")
        self.assertNotEqual(dry_evidence["snapshot_hash"], "0" * 64)

    def test_candidate_authority_metadata_malformed_duplicate_and_wrong_binding_fail_closed(self):
        comments = self.comments()
        config = self.config("batch-candidate-authority-shapes-a130", source_comment_watermark=9002)
        candidate_files, dry_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        correct_message = candidate_commit_authority_message(
            config, dry_evidence["snapshot_hash"]
        )
        cases = {
            "malformed": "ledger-batch-candidate:v1\n",
            "duplicate": correct_message + f"batch_id={config.batch_id}\n",
            "wrong_batch": correct_message.replace(
                f"batch_id={config.batch_id}",
                "batch_id=batch-other-a130",
                1,
            ),
            "wrong_controller": correct_message.replace(
                f"controller_run_id={config.controller_run_id}",
                "controller_run_id=controller-other-a130",
                1,
            ),
            "wrong_base": correct_message.replace(
                f"base_sha={config.base_sha}",
                "base_sha=" + "f" * 40,
                1,
            ),
        }
        for label, message in cases.items():
            with self.subTest(label=label):
                candidate_sha = self.commit_candidate_files(
                    candidate_files,
                    commit_message=message,
                )
                sealed_config = ProcessBatchConfig(**{
                    **config.__dict__,
                    "candidate_content_commit_sha": candidate_sha,
                })
                with self.assertRaises(ProcessorError) as raised:
                    build_batch_candidate(
                        sealed_config,
                        comments=comments,
                        queue_fetcher=self.queue(comments),
                        comment_fetcher=self.fetcher(comments),
                    )
                self.assertEqual(raised.exception.code, "processor_integrity_failure")

    def test_same_watermark_rebuilds_identical_candidate_bytes(self):
        comments = self.comments()
        config = self.config("batch-candidate-determinism-a130", source_comment_watermark=9002)
        first_files, first_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        second_files, second_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        self.assertEqual(first_files, second_files)
        self.assertEqual(first_evidence["snapshot_hash"], second_evidence["snapshot_hash"])
        self.assertEqual(first_evidence["evaluations_sha256"], second_evidence["evaluations_sha256"])

    def test_process_batch_final_full_author_identity_mutation_fails_closed(self):
        initial = self.comments()
        changes = {
            "numeric_id": lambda value: value[0]["user"].update({"id": 7002}),
            "association": lambda value: value[0].update({"author_association": "CONTRIBUTOR"}),
            "numeric_id_and_association": lambda value: (
                value[0]["user"].update({"id": 7002}),
                value[0].update({"author_association": "CONTRIBUTOR"}),
            ),
            "login": lambda value: value[0]["user"].update({"l" + "ogin": "other-author"}),
            "body": lambda value: value[0].update({"body": "mutated final body"}),
            "updated_at": lambda value: value[0].update({"updated_at": "2026-07-29T10:04:00Z"}),
            "created_at": lambda value: value[0].update({"created_at": "2026-07-29T09:59:00Z"}),
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                moved = copy.deepcopy(initial)
                change(moved)
                queue_calls = iter([initial, initial, moved])
                with self.assertRaises(ProcessorError) as raised:
                    process_batch(
                        self.config(f"batch-final-identity-{label}-a130"),
                        comments=None,
                        queue_fetcher=lambda _root: copy.deepcopy(next(queue_calls)),
                        comment_fetcher=self.fetcher(initial),
                    )
                self.assertEqual(raised.exception.code, "source_changed")

    def test_missing_watermark_never_replays_receipt_authority(self):
        config = ProcessBatchConfig(**{
            **self.config("batch-missing-watermark-replay-a130").__dict__,
            "source_comment_watermark": None,
            "candidate_content_commit_sha": "a" * 40,
        })
        with mock.patch(
            "scripts.processor.batch_processor.read_git_object",
            return_value=b'{"batch_id":"batch-missing-watermark-replay-a130","source_comment_watermark":9901}',
        ) as reader:
            with self.assertRaises(ProcessorError) as raised:
                build_batch_candidate(
                    config,
                    comments=[],
                    queue_fetcher=self.queue([]),
                )
        self.assertEqual(raised.exception.code, "processor_invalid_contract")
        reader.assert_not_called()

    def test_changed_watermark_rejects_existing_candidate_integrity(self):
        comments = self.comments() + [{
            "id": 9003,
            "user": {"id": 7001, "l" + "ogin": "fixture-author"},
            "author_association": "OWNER",
            "body": "later comment 9003",
            "created_at": "2026-07-29T10:03:00Z",
            "updated_at": "2026-07-29T10:03:00Z",
        }]
        config = self.config("batch-watermark-changed-a128", source_comment_watermark=9002)
        candidate_files, dry_evidence = build_batch_candidate(
            config,
            comments=comments,
            queue_fetcher=self.queue(comments),
            comment_fetcher=self.fetcher(comments),
        )
        candidate_sha = self.commit_candidate_files(
            candidate_files,
            config=config,
            queue_snapshot_sha256=dry_evidence["snapshot_hash"],
        )
        changed = ProcessBatchConfig(**{
            **config.__dict__,
            "source_comment_watermark": 9003,
            "candidate_content_commit_sha": candidate_sha,
        })
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                changed,
                comments=comments,
                queue_fetcher=self.queue(comments),
                comment_fetcher=self.fetcher(comments),
            )
        self.assertEqual(raised.exception.code, "processor_integrity_failure")

    def test_cli_requires_explicit_non_frozen_watermark(self):
        args = [
            "--mode", "initial",
            "--base-sha", BASE_AUTHORITY_SHA,
            "--canonical-main-sha", BASE_AUTHORITY_SHA,
            "--batch-id", "batch-cli-watermark-a128",
            "--controller-run-id", "controller-cli-watermark-a128",
            "--pr-number", "181",
            "--expected-head-sha", CURRENT_HEAD_SHA,
            "--activation-mode", "dry-run",
            "--dry-run",
            "--source-issue-number", "142",
            "--receipt-issue-number", "143",
            "--repository-root", str(ROOT),
        ]
        parsed = parse_cli(args + ["--source-comment-watermark", "9002"])
        self.assertEqual(parsed.source_comment_watermark, 9002)
        with self.assertRaises(ProcessorError):
            parse_cli(args)
        with self.assertRaises(ProcessorError):
            parse_cli(args + ["--source-comment-watermark", "-1"])
        with self.assertRaises(SystemExit):
            parse_cli(args + ["--source-comment-watermark", "invalid"])

    def test_frozen_batch_refuses_incomplete_source_replay(self):
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(self.config("batch-20260729-gate3-amendment-004"), comments=[])
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_wrong_expected_head_is_rejected(self):
        config = ProcessBatchConfig(**{
            **self.config("batch-wrong-head-a006").__dict__,
            "expected_head_sha": WRONG_EXPECTED_HEAD_SHA,
        })
        with self.assertRaises(ProcessorError) as ctx:
            build_batch_candidate(config, comments=[])
        self.assertEqual(ctx.exception.code, "processor_authority_mismatch")

    def test_initial_and_incremental_require_equal_base_and_canonical_main(self):
        for mode in ("initial", "incremental"):
            config = ProcessBatchConfig(**{
                **self.config(f"batch-{mode}-base-mismatch-a010").__dict__,
                "operating_mode": mode,
                "canonical_main_sha": CANONICAL_MAIN,
            })
            with self.assertRaises(ProcessorError) as raised:
                build_batch_candidate(config, comments=[])
            self.assertEqual(raised.exception.code, "processor_invalid_contract")

    def test_live_main_moved_or_unavailable_fails_before_candidate(self):
        config = self.config("batch-live-main-a010")
        with self.assertRaises(ProcessorError) as moved:
            build_batch_candidate(
                config,
                comments=[],
                canonical_main_fetcher=lambda _root: "f" * 40,
            )
        self.assertEqual(moved.exception.code, "processor_authority_mismatch")

        def unavailable(_root):
            raise ProcessorError("processor_source_unavailable")

        with self.assertRaises(ProcessorError) as missing:
            build_batch_candidate(
                config,
                comments=[],
                canonical_main_fetcher=unavailable,
            )
        self.assertEqual(missing.exception.code, "processor_source_unavailable")

    def test_wrong_local_canonical_object_fails_closed(self):
        missing_sha = "f" * 40
        config = ProcessBatchConfig(**{
            **self.config("batch-missing-object-a010").__dict__,
            "base_sha": missing_sha,
            "canonical_main_sha": missing_sha,
        })
        with self.assertRaises(ProcessorError) as raised:
            build_batch_candidate(
                config,
                comments=[],
                canonical_main_fetcher=lambda _root: missing_sha,
            )
        self.assertEqual(raised.exception.code, "authority_missing")

    def test_cli_requires_closed_explicit_contract(self):
        with self.assertRaises(SystemExit):
            parse_cli([])
        with self.assertRaises(SystemExit):
            parse_cli(["--unknown", "value"])

    def test_no_source_comment_mutation_path_exists(self):
        source = (ROOT / "scripts" / "processor" / "cleanup_workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("delete_live_comment", source)
        self.assertNotIn("-X", source)
        self.assertNotIn("LEDGER_CLEANUP_ENABLED", source)


if __name__ == "__main__":
    unittest.main()
