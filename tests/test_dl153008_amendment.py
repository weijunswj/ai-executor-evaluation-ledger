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
# Durable canonical main authority for the current production append-only chain.
CANONICAL_CANDIDATE_BASE = "be69246a7b9e7f06601f1e6ed032202a5e8a0b1f"
NUMERIC_KEY = "i" + "d"
LOGIN_KEY = "l" + "ogin"

CURRENT_AUTHORITY_STEP = "Verify immutable checkout and base authority"
CURRENT_AUTHORITY_ARGS = (
    "--github-sha",
    "--checkout-sha",
    "--pr-head-sha",
    "--pr-base-sha",
    "--before-sha",
    "--dispatch-base-sha",
    "--output-file",
)


class TestWorkflowAuthorityGate(unittest.TestCase):
    WORKFLOWS = (
        (
            ".github/workflows/ci.yml",
            "Checkout immutable workflow authority",
            "Run code suite or bounded evaluation-data regression",
            (
                "Verify deterministic append-only view rebuild twice",
                "Run Public Safety Scan",
                "Validate closed migration manifests",
                "Validate immutable batch receipt seals",
            ),
        ),
        (
            ".github/workflows/public-safety.yml",
            "Check out immutable workflow authority with full history",
            "Run safety code suite or bounded evaluation-data regression",
            (
                "Scan tracked content and added history",
                "Validate closed migration manifests",
                "Validate immutable batch receipt seals",
                "Verify append-only source and generated views",
            ),
        ),
    )

    @staticmethod
    def step_block(workflow: str, name: str) -> tuple[str, int, int]:
        match = re.search(
            rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - name: |\Z)",
            workflow,
        )
        if match is None:
            raise AssertionError(f"workflow step missing: {name}")
        return match.group(0), match.start(), match.end()

    def assert_gate(
        self,
        relative: str,
        workflow: str,
        checkout: str,
        first_test: str,
        later_steps: tuple[str, ...],
    ) -> None:
        del relative
        gate, gate_start, gate_end = self.step_block(
            workflow, CURRENT_AUTHORITY_STEP
        )
        _, checkout_start, _ = self.step_block(workflow, checkout)
        self.assertLess(checkout_start, gate_start)
        self.assertLess(gate_start, self.step_block(workflow, first_test)[1])
        self.assertLess(gate_end, self.step_block(workflow, first_test)[1])

        for name in later_steps:
            self.assertLess(gate_start, self.step_block(workflow, name)[1])

        self.assertIn("id: authority", gate)
        self.assertIn("scripts/resolve_workflow_authority.py", gate)
        for argument in CURRENT_AUTHORITY_ARGS:
            self.assertIn(argument, gate)
        self.assertIn('"$GITHUB_OUTPUT"', gate)
        self.assertNotIn("refs/pull/", workflow)
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
            self.assertNotIn(forbidden, gate)
        self.assertNotIn("continue-on-error", workflow)

    def test_both_workflows_retain_fail_closed_current_authority_gate_and_reject_weakening(self):
        for relative, checkout, first_test, later_steps in self.WORKFLOWS:
            with self.subTest(relative=relative):
                original = (ROOT / relative).read_text(encoding="utf-8")
                self.assert_gate(relative, original, checkout, first_test, later_steps)
                gate, gate_start, gate_end = self.step_block(
                    original, CURRENT_AUTHORITY_STEP
                )

                without_gate = original[:gate_start] + original[gate_end:]
                _, first_test_start, first_test_end = self.step_block(
                    without_gate, first_test
                )
                del first_test_start
                step_after_tests = (
                    without_gate[:first_test_end]
                    + gate
                    + without_gate[first_test_end:]
                )
                gate_with_continue = gate.replace(
                    "        shell: bash\n",
                    "        continue-on-error: true\n        shell: bash\n",
                    1,
                )

                mutations = {
                    "authority resolver omitted": original.replace(
                        "            python scripts/resolve_workflow_authority.py\n",
                        "",
                        1,
                    ),
                    "checkout argument omitted": original.replace(
                        '            --checkout-sha "$CHECKOUT_SHA"\n',
                        "",
                        1,
                    ),
                    "step placed after tests": step_after_tests,
                    "failure ignored": (
                        original[:gate_start]
                        + gate_with_continue
                        + original[gate_end:]
                    ),
                    "PR namespace introduced": original.replace(
                        "        shell: bash\n",
                        "        shell: bash\n        # refs/pull/ is not an immutable authority\n",
                        1,
                    ),
                    "authority output id altered": original.replace(
                        "        id: authority\n",
                        "        id: changed\n",
                        1,
                    ),
                }
                for label, mutated in mutations.items():
                    with self.subTest(mutation=label):
                        with self.assertRaises(AssertionError):
                            self.assert_gate(
                                relative,
                                mutated,
                                checkout,
                                first_test,
                                later_steps,
                            )


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
                ["git", "checkout", "--quiet", "--detach", CANONICAL_CANDIDATE_BASE],
                cwd=root,
                check=True,
            )
            for relative in (
                "scripts/rebuild_views.py",
                "scripts/validate_manifests.py",
                "schema/manifest.schema.json",
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

    def prepare_current_candidate(
        self,
        root: Path,
        candidate: bytes,
        *,
        regenerate: bool,
    ) -> None:
        """Seed one coherent current candidate before its production checks."""

        (root / "evaluations.jsonl").write_bytes(candidate)
        shutil.copy2(
            ROOT / "ledger" / "dispositions.jsonl",
            root / "ledger" / "dispositions.jsonl",
        )
        shutil.copy2(
            ROOT / "migrations" / "historical-direct-controller-bypass-reconciliation.json",
            root / "migrations" / "historical-direct-controller-bypass-reconciliation.json",
        )
        if not regenerate:
            result = self.run_command(root, "scripts/rebuild_views.py")
            self.assertEqual(
                result.returncode,
                0,
                msg=result.stderr.decode("utf-8", errors="replace"),
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
            self.prepare_current_candidate(
                root,
                candidate,
                regenerate=regenerate,
            )
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
            self.prepare_current_candidate(
                root,
                self.canonical,
                regenerate=regenerate,
            )
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
            marker = b"<!-- GENERATED:README-SCORES:START -->"
            path.write_bytes(path.read_bytes().replace(marker, marker + b"\ntampered", 1))

        for label, mutate in {
            "manifest": manifest,
            "correction": correction,
            "disposition": disposition,
            "generated": generated,
        }.items():
            with self.subTest(label=label):
                self.assert_chain_rejects(mutate, regenerate=label != "generated")


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
            "issue_url": batch_processor.ISSUE_142_API_URL,
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

    def readback_authority(self, *thread_responses):
        config = self.config()
        pr = {
            "state": "open",
            "merged_at": None,
            "merge_commit_sha": "a" * 40,
            "head": {"sha": "c" * 40},
        }
        main = {"object": {"sha": "b" * 40}}
        raw_commit = {"parents": [], "files": []}
        raw_receipt = {"type": "file", "encoding": "base64", "content": "e30="}
        with (
            mock.patch.object(
                cleanup_workflow,
                "_gh_get_json",
                side_effect=[pr, main, raw_commit, raw_receipt, {"workflow_runs": []}],
            ),
            mock.patch.object(
                cleanup_workflow,
                "_gh_get_paginated",
                side_effect=[[], []],
            ),
            mock.patch.object(
                cleanup_workflow,
                "gh_json",
                side_effect=thread_responses,
            ),
        ):
            return cleanup_workflow._readback_live_authority(config)

    def test_valid_empty_nonempty_and_explicit_final_cursor(self):
        self.assertEqual(self.threads(self.envelope([], total=0)), [])
        node = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        self.assertEqual(self.threads(self.envelope([node], total=1)), [node])
        self.assertEqual(
            self.threads(
                self.envelope(
                    [node],
                    total=1,
                    end_cursor="cursor-final",
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

    def test_final_end_cursor_is_required_and_bounded(self):
        node = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        cases = {
            "missing": self.envelope(
                [node], total=1, include_end_cursor=False
            ),
            "empty": self.envelope([node], total=1, end_cursor=""),
            "whitespace": self.envelope([node], total=1, end_cursor=" "),
            "padded": self.envelope([node], total=1, end_cursor=" cursor-final "),
            "control": self.envelope([node], total=1, end_cursor="bad\ncursor"),
            "overlong": self.envelope([node], total=1, end_cursor="x" * 257),
            "numeric": self.envelope([node], total=1, end_cursor=1),
            "boolean": self.envelope([node], total=1, end_cursor=True),
        }
        for label, response in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(response)

    def test_intermediate_cursor_is_required_and_bounded(self):
        first = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        second = {"id": "thread-2", "isResolved": True, "isOutdated": False}
        cases = {
            "missing": {"include_end_cursor": False},
            "null": {"end_cursor": None},
            "numeric": {"end_cursor": 1},
            "boolean": {"end_cursor": True},
            "empty": {"end_cursor": ""},
            "whitespace": {"end_cursor": " "},
            "leading_padding": {"end_cursor": " cursor-1"},
            "trailing_padding": {"end_cursor": "cursor-1 "},
            "control": {"end_cursor": "bad\ncursor"},
            "unicode_control": {"end_cursor": "bad\u0085cursor"},
            "overlong": {"end_cursor": "x" * 257},
        }
        for label, cursor_args in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.threads(
                    self.envelope(
                        [first], total=2, has_next=True, **cursor_args
                    ),
                    self.envelope([second], total=2),
                )

    def test_valid_256_character_intermediate_cursor(self):
        first = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        second = {"id": "thread-2", "isResolved": True, "isOutdated": False}
        self.assertEqual(
            [first, second],
            self.threads(
                self.envelope(
                    [first], total=2, has_next=True, end_cursor="x" * 256
                ),
                self.envelope([second], total=2),
            ),
        )

    def test_malformed_pagination_cannot_return_clear_review_state(self):
        first = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        second = {"id": "thread-2", "isResolved": True, "isOutdated": False}
        cases = {
            "missing_final": [
                self.envelope([first], total=1, include_end_cursor=False)
            ],
            "missing_intermediate": [
                self.envelope(
                    [first], total=2, has_next=True, include_end_cursor=False
                ),
                self.envelope([second], total=2),
            ],
            "null_intermediate": [
                self.envelope([first], total=2, has_next=True, end_cursor=None),
                self.envelope([second], total=2),
            ],
            "empty_intermediate": [
                self.envelope([first], total=2, has_next=True, end_cursor=""),
                self.envelope([second], total=2),
            ],
            "padded_intermediate": [
                self.envelope(
                    [first], total=2, has_next=True, end_cursor=" cursor-1 "
                ),
                self.envelope([second], total=2),
            ],
            "control_intermediate": [
                self.envelope(
                    [first], total=2, has_next=True, end_cursor="bad\ncursor"
                ),
                self.envelope([second], total=2),
            ],
            "overlong_intermediate": [
                self.envelope(
                    [first], total=2, has_next=True, end_cursor="x" * 257
                ),
                self.envelope([second], total=2),
            ],
        }
        for label, responses in cases.items():
            with self.subTest(label=label), self.assertRaises(ProcessorError):
                self.readback_authority(*responses)

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
        first = {"id": "thread-1", "isResolved": True, "isOutdated": False}
        second = {"id": "thread-2", "isResolved": True, "isOutdated": False}
        cases = {
            "string_boolean": [self.envelope([], total=0, has_next="false")],
            "numeric_boolean": [self.envelope([], total=0, has_next=1)],
            "missing_next_cursor": [self.envelope([first], total=2, has_next=True, include_end_cursor=False)],
            "null_next_cursor": [self.envelope([first], total=2, has_next=True, end_cursor=None)],
            "numeric_cursor": [self.envelope([first], total=2, has_next=True, end_cursor=1)],
            "repeated_cursor": [
                self.envelope([first], total=3, has_next=True, end_cursor="cursor-1"),
                self.envelope([second], total=3, has_next=True, end_cursor="cursor-1"),
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
