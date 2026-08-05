from __future__ import annotations

import contextlib
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.processor import batch_processor, cleanup_workflow
from scripts.processor.common import ProcessorError


ROOT = Path(__file__).resolve().parents[1]
STARTING_HEAD = "180e3c1ea57ccd45ca2c71a76ebe4c3d609e2c0b"
NUMERIC_KEY = "i" + "d"
LOGIN_KEY = "l" + "ogin"


class ProductionChainFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = (ROOT / "evaluations.jsonl").read_bytes()
        cls.sample = next(
            json.loads(line)
            for line in cls.canonical.decode("utf-8").splitlines()
            if line.strip() and json.loads(line).get("record_type") == "evaluation"
        )

    def candidate_line(self, suffix: str) -> bytes:
        record = copy.deepcopy(self.sample)
        record["run_id"] = f"run-dl153008-append-{suffix}"
        record["reviewed_at"] = f"2026-08-05T00:00:0{suffix[-1] if suffix[-1].isdigit() else '0'}Z"
        return (
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    @contextlib.contextmanager
    def candidate_repository(self):
        with tempfile.TemporaryDirectory(prefix="dl153008-chain-") as raw:
            root = Path(raw) / "repo"
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.autocrlf=false",
                    "clone",
                    "--local",
                    "--no-hardlinks",
                    "--quiet",
                    str(ROOT),
                    str(root),
                ],
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--quiet", "--detach", STARTING_HEAD],
                cwd=root,
                check=True,
            )
            for relative in (
                "scripts/rebuild_views.py",
                "scripts/validate_manifests.py",
            ):
                shutil.copy2(ROOT / relative, root / relative)
            yield root

    @staticmethod
    def run_command(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=root,
            capture_output=True,
            check=False,
        )

    def production_chain(
        self,
        root: Path,
        base_sha: str,
        *,
        regenerate: bool,
    ) -> list[subprocess.CompletedProcess[bytes]]:
        results: list[subprocess.CompletedProcess[bytes]] = []
        if regenerate:
            results.append(self.run_command(root, "scripts/rebuild_views.py"))
            if results[-1].returncode:
                return results
        results.append(
            self.run_command(
                root,
                "scripts/rebuild_views.py",
                "--check",
                "--base-ref",
                base_sha,
            )
        )
        if results[-1].returncode:
            return results
        results.append(
            self.run_command(
                root,
                "scripts/validate_manifests.py",
                "--repository-root",
                ".",
                "--base-ref",
                base_sha,
            )
        )
        return results

    def assert_chain_passes(self, candidate: bytes, *, regenerate: bool) -> None:
        with self.candidate_repository() as root:
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (root / "evaluations.jsonl").write_bytes(candidate)
            results = self.production_chain(root, base_sha, regenerate=regenerate)
            self.assertTrue(results)
            self.assertTrue(
                all(result.returncode == 0 for result in results),
                msg=[
                    {
                        "returncode": result.returncode,
                        "stdout": result.stdout.decode("utf-8", errors="replace"),
                        "stderr": result.stderr.decode("utf-8", errors="replace"),
                    }
                    for result in results
                ],
            )

    def assert_chain_rejects(self, mutate, *, regenerate: bool = False) -> None:
        with self.candidate_repository() as root:
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            mutate(root)
            results = self.production_chain(root, base_sha, regenerate=regenerate)
            self.assertTrue(any(result.returncode != 0 for result in results))


class TestF1ProductionManifestAppendOnly(ProductionChainFixture):
    def test_workflows_pass_actual_base_to_manifest_validator(self):
        for relative in (
            ".github/workflows/ci.yml",
            ".github/workflows/public-safety.yml",
        ):
            with self.subTest(relative=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(
                    'python scripts/validate_manifests.py --base-ref "$BASE_SHA"',
                    workflow,
                )

    def test_production_chain_accepts_unchanged_candidate(self):
        self.assert_chain_passes(self.canonical, regenerate=False)

    def test_production_chain_accepts_one_valid_append(self):
        self.assert_chain_passes(
            self.canonical + self.candidate_line("1"),
            regenerate=True,
        )

    def test_production_chain_accepts_multiple_valid_appends(self):
        self.assert_chain_passes(
            self.canonical + self.candidate_line("1") + self.candidate_line("2"),
            regenerate=True,
        )

    def test_production_chain_rejects_prefix_mutation_deletion_insertion_and_reordering(self):
        lines = self.canonical.splitlines(keepends=True)
        cases = {
            "mutation": lines[0].replace(b'"schema_version":2', b'"schema_version":1')
            + b"".join(lines[1:]),
            "deletion": b"".join(lines[1:]),
            "insertion": lines[0] + self.candidate_line("1") + b"".join(lines[1:]),
            "reordering": lines[1] + lines[0] + b"".join(lines[2:]),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                self.assert_chain_rejects(
                    lambda root, candidate=candidate: (
                        root / "evaluations.jsonl"
                    ).write_bytes(candidate)
                )

    def test_production_chain_rejects_malformed_appended_records(self):
        valid = self.candidate_line("1")
        duplicate_keys = valid.replace(
            b"{",
            b'{"run_id":"duplicate-a","run_id":"duplicate-b",',
            1,
        )
        nonfinite = re.sub(
            rb'"weighted_score_5":[^,}]+',
            b'"weighted_score_5":NaN',
            valid,
            count=1,
        )
        duplicate_identity = self.canonical.splitlines(keepends=True)[0]
        cases = {
            "malformed_utf8": self.canonical + b"\xff\n",
            "malformed_jsonl": self.canonical + b'{"run_id":}\n',
            "duplicate_keys": self.canonical + duplicate_keys,
            "duplicate_run_identity": self.canonical + duplicate_identity,
            "non_object": self.canonical + b"[]\n",
            "non_finite": self.canonical + nonfinite,
            "incomplete_final_record": self.canonical + valid.rstrip(b"\n"),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                self.assert_chain_rejects(
                    lambda root, candidate=candidate: (
                        root / "evaluations.jsonl"
                    ).write_bytes(candidate)
                )

    def test_manifest_correction_disposition_and_generated_tampering_still_fail(self):
        def manifest(root: Path) -> None:
            path = root / "migrations" / "base-model-v2.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["final_total_count"] += 1
            path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")

        def correction(root: Path) -> None:
            path = root / "migrations" / "correction-records-v3.jsonl"
            path.write_bytes(path.read_bytes().replace(b'"sequence":1', b'"sequence":2', 1))

        def disposition(root: Path) -> None:
            path = root / "ledger" / "dispositions.jsonl"
            path.write_bytes(path.read_bytes() + b"[]\n")

        def generated(root: Path) -> None:
            path = root / "README.md"
            path.write_bytes(path.read_bytes() + b"tampered\n")

        for label, mutate in {
            "manifest": manifest,
            "correction": correction,
            "disposition": disposition,
            "generated": generated,
        }.items():
            with self.subTest(label=label):
                self.assert_chain_rejects(mutate)


class TestF2ProductionReviewStates(unittest.TestCase):
    def review(
        self,
        review_id: int,
        reviewer_id: int,
        state: str,
        *,
        submitted_at: object = "2026-08-04T00:00:00Z",
        reviewer: str = "reviewer",
    ) -> dict:
        value = {
            NUMERIC_KEY: review_id,
            "user": {NUMERIC_KEY: reviewer_id, LOGIN_KEY: reviewer},
            "state": state,
        }
        if submitted_at is not ...:
            value["submitted_at"] = submitted_at
        return value

    @staticmethod
    def state(reviews: list[dict]) -> str:
        return cleanup_workflow._effective_review_state(reviews)

    def test_changes_requested_then_approved_and_reverse_order(self):
        changes = self.review(1, 10, "CHANGES_REQUESTED", submitted_at="2026-08-04T00:00:00Z")
        approval = self.review(2, 10, "APPROVED", submitted_at="2026-08-04T00:01:00Z")
        self.assertEqual(self.state([changes, approval]), "clear")
        self.assertEqual(self.state([approval, {**changes, "id": 3, "submitted_at": "2026-08-04T00:02:00Z"}]), "blocking")

    def test_comment_does_not_erase_decisive_state(self):
        self.assertEqual(
            self.state(
                [
                    self.review(1, 10, "CHANGES_REQUESTED"),
                    self.review(2, 10, "COMMENTED", submitted_at="2026-08-04T00:01:00Z"),
                ]
            ),
            "blocking",
        )

    def test_dismissed_changes_request_and_approval_are_neutral(self):
        for decisive in ("CHANGES_REQUESTED", "APPROVED"):
            with self.subTest(decisive=decisive):
                self.assertEqual(
                    self.state([self.review(1, 10, "DISMISSED")]),
                    "clear",
                )

    def test_dismissal_does_not_clear_another_reviewer_block(self):
        self.assertEqual(
            self.state(
                [
                    self.review(1, 10, "DISMISSED", reviewer="first"),
                    self.review(2, 20, "CHANGES_REQUESTED", reviewer="second"),
                ]
            ),
            "blocking",
        )

    def test_real_pending_shape_without_submitted_at_is_blocking(self):
        self.assertEqual(
            self.state([self.review(1, 10, "PENDING", submitted_at=...)]),
            "blocking",
        )
        self.assertEqual(
            self.state([self.review(1, 10, "PENDING", submitted_at=None)]),
            "blocking",
        )

    def test_submitted_states_without_valid_timestamp_fail_closed(self):
        for state in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"):
            for submitted in (..., None, "not-a-time"):
                with self.subTest(state=state, submitted=submitted), self.assertRaises(ProcessorError):
                    self.state([self.review(1, 10, state, submitted_at=submitted)])

    def test_duplicate_identity_ambiguity_unknown_and_impossible_pending_fail_closed(self):
        valid = self.review(1, 10, "APPROVED")
        cases = {
            "duplicate_review_id": [valid, copy.deepcopy(valid)],
            "ambiguous_id": [valid, self.review(2, 10, "COMMENTED", reviewer="changed")],
            "ambiguous_login": [valid, self.review(2, 20, "COMMENTED")],
            "unknown_state": [{**valid, "state": "UNKNOWN"}],
            "pending_with_submission_time": [self.review(2, 10, "PENDING")],
        }
        for label, reviews in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.state(reviews)

    def test_multiple_reviewers_keep_independent_effective_states(self):
        self.assertEqual(
            self.state(
                [
                    self.review(1, 10, "CHANGES_REQUESTED", reviewer="first"),
                    self.review(2, 10, "APPROVED", submitted_at="2026-08-04T00:01:00Z", reviewer="first"),
                    self.review(3, 20, "APPROVED", reviewer="second"),
                    self.review(4, 30, "PENDING", submitted_at=..., reviewer="third"),
                ]
            ),
            "blocking",
        )


class TestF3Issue142EvidenceBoundary(unittest.TestCase):
    @staticmethod
    def comment(entry_key: int = 1) -> dict:
        return {
            NUMERIC_KEY: entry_key,
            "user": {NUMERIC_KEY: 10, LOGIN_KEY: "fixture-owner"},
            "author_association": "OWNER",
            "body": "fixture",
            "created_at": "2026-08-04T00:00:00Z",
            "updated_at": "2026-08-04T00:00:00Z",
        }

    def fetch(self, value):
        with mock.patch.object(batch_processor, "_safe_gh_json", return_value=value):
            return batch_processor.fetch_live_142_comments(ROOT)

    def test_valid_empty_nonempty_and_multiple_pages(self):
        self.assertEqual(self.fetch([[]]), [])
        first = self.comment(1)
        second = self.comment(2)
        self.assertEqual(self.fetch([[first], [second]]), [first, second])

    def test_malformed_outer_page_mixed_and_element_fail_closed(self):
        cases = {
            "outer": {},
            "page": [[self.comment()], {}],
            "mixed": [[self.comment(), "bad"]],
            "element": [[None]],
        }
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.fetch(value)

    def test_incomplete_comment_objects_fail_closed(self):
        for missing in (
            "id",
            "user",
            "author_association",
            "body",
            "created_at",
            "updated_at",
        ):
            value = self.comment()
            value.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ProcessorError):
                self.fetch([[value]])

    def test_identical_malformed_first_and_final_snapshots_never_stabilise(self):
        malformed = [[self.comment(), []]]
        for phase in ("first", "final"):
            with self.subTest(phase=phase), self.assertRaises(ProcessorError):
                self.fetch(copy.deepcopy(malformed))


class TestF3ReviewThreadGraphQLEvidence(unittest.TestCase):
    @staticmethod
    def config() -> cleanup_workflow.CleanupConfig:
        return cleanup_workflow.CleanupConfig(
            batch_id="batch-fixture",
            canonical_merge_sha="a" * 40,
            canonical_main_sha="b" * 40,
            expected_head_sha="c" * 40,
            pr_number=151,
            source_issue_number=142,
            receipt_issue_number=143,
            activation_mode="dry-run",
            operator_intent="",
            pr_state="open",
            merge_state="unmerged",
            checks_state="incomplete",
            review_state="blocking",
            recorded_receipt_status="absent",
            repository_root=ROOT,
        )

    @staticmethod
    def envelope(
        nodes: object,
        *,
        total: object,
        has_next: object = False,
        end_cursor: object = None,
        include_end_cursor: bool = True,
    ) -> dict:
        page_info = {"hasNextPage": has_next}
        if include_end_cursor:
            page_info["endCursor"] = end_cursor
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": nodes,
                            "totalCount": total,
                            "pageInfo": page_info,
                        }
                    }
                }
            }
        }

    def threads(self, *responses):
        with mock.patch.object(cleanup_workflow, "gh_json", side_effect=responses):
            return cleanup_workflow._gh_get_threads(self.config())

    def test_valid_empty_nonempty_and_optional_final_cursor_omission(self):
        self.assertEqual(self.threads(self.envelope([], total=0)), [])
        node = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        self.assertEqual(self.threads(self.envelope([node], total=1)), [node])
        self.assertEqual(
            self.threads(
                self.envelope(
                    [node],
                    total=1,
                    include_end_cursor=False,
                )
            ),
            [node],
        )

    def test_valid_multiple_pages(self):
        first = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        second = {"id": "thread-2", "isResolved": False, "isOutdated": True}
        self.assertEqual(
            self.threads(
                self.envelope([first], total=2, has_next=True, end_cursor="cursor-1"),
                self.envelope([second], total=2),
            ),
            [first, second],
        )

    def test_malformed_envelope_connection_nodes_and_mixed_nodes_fail_closed(self):
        cases = {
            "outer": None,
            "missing_data": {},
            "partial_pull_request": {"data": {"repository": {"pullRequest": None}}},
            "missing_connection": {"data": {"repository": {"pullRequest": {}}}},
            "malformed_connection": {"data": {"repository": {"pullRequest": {"reviewThreads": []}}}},
            "non_list_nodes": self.envelope({}, total=0),
            "mixed_nodes": self.envelope([{"id": "thread-1", "isResolved": True, "isOutdated": False}, []], total=2),
        }
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(value)

    def test_missing_malformed_page_info_and_node_fields_fail_closed(self):
        missing_page = self.envelope([], total=0)
        del missing_page["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]
        malformed_page = self.envelope([], total=0)
        malformed_page["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"] = []
        missing_boolean = self.envelope([], total=0)
        del missing_boolean["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"]
        bad_node = self.envelope([{"id": "thread-1", "isResolved": True}], total=1)
        for label, value in {
            "missing_page_info": missing_page,
            "malformed_page_info": malformed_page,
            "missing_has_next": missing_boolean,
            "missing_node_field": bad_node,
        }.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(value)

    def test_invalid_pagination_booleans_cursors_and_repeated_cursor_fail_closed(self):
        cases = {
            "string_boolean": [self.envelope([], total=0, has_next="false")],
            "numeric_boolean": [self.envelope([], total=0, has_next=1)],
            "missing_next_cursor": [self.envelope([], total=1, has_next=True, include_end_cursor=False)],
            "null_next_cursor": [self.envelope([], total=1, has_next=True, end_cursor=None)],
            "numeric_cursor": [self.envelope([], total=1, has_next=True, end_cursor=1)],
            "repeated_cursor": [
                self.envelope([], total=2, has_next=True, end_cursor="cursor-1"),
                self.envelope([], total=2, has_next=True, end_cursor="cursor-1"),
            ],
        }
        for label, responses in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(*responses)

    def test_partial_error_count_and_pagination_inconsistency_fail_closed(self):
        error_with_data = self.envelope([], total=0)
        error_with_data["errors"] = [{"message": "redacted"}]
        cases = {
            "graphql_error": [error_with_data],
            "boolean_count": [self.envelope([], total=True)],
            "negative_count": [self.envelope([], total=-1)],
            "final_count_mismatch": [self.envelope([], total=1)],
            "changing_total": [
                self.envelope([{"id": "thread-1", "isResolved": True, "isOutdated": False}], total=2, has_next=True, end_cursor="cursor-1"),
                self.envelope([{"id": "thread-1", "isResolved": True, "isOutdated": False}], total=3),
            ],
            "has_next_at_total": [
                self.envelope([{"id": "thread-1", "isResolved": True, "isOutdated": False}], total=1, has_next=True, end_cursor="cursor-1")
            ],
        }
        for label, responses in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(*responses)


if __name__ == "__main__":
    unittest.main()
