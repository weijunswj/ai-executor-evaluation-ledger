from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_public_safety as public_safety
from scripts import rebuild_views
from scripts.validate_receipts import (
    LEGACY_FROZEN_RECEIPT_AUTHORITY,
    _running_on_canonical_main,
)

ROOT = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def init_fixture_repo(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")
    git(root, 'config', 'user.name', 'ledger-fixture')
    git(root, 'config', 'user.email', 'fixture' + '@' + 'example.invalid')


def nested_candidate_tree(base: Path) -> Path:
    candidate = base / 'repository' / '.git' / 'candidate'
    candidate.mkdir(parents=True)
    return candidate


def write_candidate_jsonl(candidate: Path, raw: bytes) -> Path:
    path = candidate / 'ledger' / 'dispositions.jsonl'
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    return path


def luna_identity() -> str:
    return '-'.join(('GPT', '5')) + '.6 ' + ' '.join(('Luna', 'Max'))


def commit_blob(root: Path, relative: str, data: bytes, message: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git(root, 'add', relative)
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')


def commit_delete(root: Path, relative: str, message: str) -> str:
    git(root, 'rm', '-q', relative)
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')


def luna_rule_set_sha256(rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    structures = []
    for rule_id, sequence in rules:
        sequence_bytes = (
            json.dumps(sequence, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        structures.append(
            {
                "case_folding": "unicode_casefold",
                "normalized_sequence_sha256": hashlib.sha256(
                    sequence_bytes
                ).hexdigest(),
                "normalization": "NFKC",
                "rule_id": rule_id,
                "token_count": len(sequence),
                "tokenization": "unicode_alphanumeric_runs_v1",
            }
        )
    canonical = (
        json.dumps(
            structures,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class TestControllerLedgerMaintenance(unittest.TestCase):
    @staticmethod
    def _receipt_route_block(workflow: str) -> str:
        start = workflow.index("          legacy_context=false")
        end = workflow.index("\n\n      - name:", start)
        return workflow[start:end]


    @staticmethod
    def _bash_command() -> str:
        candidates = ["bash"]
        if os.name == "nt":
            candidates = [
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
                "bash",
            ]
        for candidate in candidates:
            try:
                probe = subprocess.run(
                    [candidate, "--noprofile", "--norc", "-c", "exit 0"],
                    capture_output=True,
                    check=False,
                )
            except OSError:
                continue
            if probe.returncode == 0:
                return candidate
        raise AssertionError("A working Bash executable is required for workflow route tests")

    def _run_push_route(
        self,
        workflow: str,
        root: Path,
        base_sha: str,
        head_sha: str,
    ) -> subprocess.CompletedProcess[str]:
        block = self._receipt_route_block(workflow)
        start = block.index("          legacy_context=false")
        end = block.index(
            '\n          elif [[ "$EVENT_NAME" == "workflow_dispatch" ]]; then',
            start,
        )
        push_prefix = block[start:end]
        script = (
            push_prefix
            + "\n          fi\n"
            + "echo route_completed\n"
            + "echo legacy_context=$legacy_context\n"
            + "echo canonical_main_context=$canonical_main_context\n"
            + "echo canonical_main_historical_context=$canonical_main_historical_context\n"
            + "echo canonical_base_context=$canonical_base_context\n"
        )
        environment = os.environ.copy()
        environment.update(
            {
                "EVENT_NAME": "push",
                "REF_NAME": "main",
                "HEAD_SHA": head_sha,
                "BASE_SHA": base_sha,
            }
        )
        return subprocess.run(
            [self._bash_command(), "--noprofile", "--norc", "-eu", "-c", script],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_receipt_routes_are_aligned_and_fail_closed(self):
        blocks = []
        receipt_delta = (
            'receipt_delta=$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" '
            '-- ledger/receipts/batches)'
        )
        receipt_bound_delta = (
            'receipt_bound_delta=$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" '
            '-- evaluations.jsonl ledger/dispositions.jsonl README.md scorecard.md '
            'analysis/model-recommendation.json)'
        )
        strict_pr_route = (
            'args=(python scripts/validate_receipts.py --mode pr '
            '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
            '--validation-level source-replay)'
        )
        current_main_route = (
            'args=(python scripts/validate_receipts.py --mode canonical-main '
            '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
            '--validation-level source-replay)'
        )
        historical_main_route = (
            'args=(python scripts/validate_receipts.py --mode canonical-main '
            '--authority-sha "$HEAD_SHA" --validation-level source-replay)'
        )
        canonical_base_route = (
            'args=(python scripts/validate_receipts.py --mode canonical-main '
            '--authority-sha "$BASE_SHA" --canonical-base-sha '
            '"$BASE_PARENT_SHA" --validation-level source-replay)'
        )
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            block = self._receipt_route_block(workflow)
            blocks.append(block)
            with self.subTest(workflow=relative):
                self.assertIn("canonical_main_historical_context=false", block)
                self.assertIn("canonical_base_context=false", block)
                self.assertEqual(2, block.count(receipt_delta))
                self.assertEqual(2, block.count(receipt_bound_delta))
                ordinary_pr = 'elif [[ "$EVENT_NAME" == "pull_request" ]]; then'
                self.assertIn(ordinary_pr, block)
                self.assertLess(
                    block.index('"$HEAD_REF" == controller/evaluation-*'),
                    block.index(ordinary_pr),
                )
                self.assertLess(
                    block.index('"$HEAD_REF" == controller/ledger-maintenance-*'),
                    block.index(ordinary_pr),
                )
                self.assertEqual(
                    1,
                    block.count(
                        'full_delta=$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" | sort)'
                    ),
                )
                self.assertEqual(
                    1,
                    block.count(
                        "supported_evaluation_delta=$(printf '%s\\n' evaluations.jsonl README.md scorecard.md analysis/model-recommendation.json | sort)"
                    ),
                )
                self.assertIn(
                    'if [[ "$EVENT_NAME" == "push" && "$REF_NAME" == "main" ]]; then\n'
                    f"            {receipt_delta}\n"
                    f"            {receipt_bound_delta}\n"
                    '            full_delta=$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" | sort)\n'
                    "            supported_evaluation_delta=$(printf '%s\\n' evaluations.jsonl README.md scorecard.md analysis/model-recommendation.json | sort)\n"
                    '            if [[ -n "$receipt_delta" ]]; then\n'
                    "              canonical_main_context=true\n"
                    '            elif [[ "$full_delta" == "$supported_evaluation_delta" ]]; then\n'
                    "              canonical_main_historical_context=true\n"
                    '            elif [[ -n "$receipt_bound_delta" ]]; then\n'
                    "              printf '%s\\n' 'Canonical receipt-bound data changed without a receipt.' >&2\n"
                    "              exit 1\n"
                    "            else\n"
                    "              canonical_main_historical_context=true\n"
                    "            fi",
                    block,
                )
                push_start = block.index(
                    'if [[ "$EVENT_NAME" == "push" && "$REF_NAME" == "main" ]]; then'
                )
                push_end = block.index(
                    '\n          elif [[ "$EVENT_NAME" == "workflow_dispatch" ]]; then',
                    push_start,
                )
                self.assertNotIn("legacy_context=true", block[push_start:push_end])
                self.assertIn(
                    'elif [[ "$EVENT_NAME" == "workflow_dispatch" ]]; then\n'
                    '            if [[ "$REF_NAME" != "main" ]]; then\n'
                    "              printf '%s\\n' 'Canonical main receipt validation target is ambiguous.' >&2\n"
                    "              exit 1\n"
                    "            fi\n"
                    "            canonical_main_context=true",
                    block,
                )
                self.assertIn(
                    f"{ordinary_pr}\n"
                    f"            {receipt_delta}\n"
                    f"            {receipt_bound_delta}\n"
                    '            if [[ -z "$receipt_delta" && -z "$receipt_bound_delta" ]]; then\n'
                    "              canonical_base_context=true\n"
                    "            fi",
                    block,
                )
                fail_closed_tail = (
                    "\n              printf '%s\\n' 'Canonical base receipt topology is invalid.' >&2\n"
                    "              exit 1\n"
                    "            fi"
                )
                for guard in (
                    'if [[ ! "$BASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then',
                    'if ! resolved_base_sha=$(git rev-parse --verify "$BASE_SHA^{commit}"); then',
                    'if [[ "$resolved_base_sha" != "$BASE_SHA" ]]; then',
                    'if ! base_parent_line=$(git rev-list --parents -n 1 "$BASE_SHA"); then',
                    'if [[ "${#base_parent_fields[@]}" -ne 2 ]]; then',
                    'if [[ "${base_parent_fields[0]}" != "$BASE_SHA" ]]; then',
                    'if [[ ! "$BASE_PARENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then',
                    'if ! resolved_base_parent_sha=$(git rev-parse --verify "$BASE_PARENT_SHA^{commit}"); then',
                    'if [[ "$resolved_base_parent_sha" != "$BASE_PARENT_SHA" ]]; then',
                ):
                    self.assertIn(guard + fail_closed_tail, block)
                self.assertIn('read -r -a base_parent_fields <<< "$base_parent_line"', block)
                self.assertIn('BASE_PARENT_SHA="${base_parent_fields[1]}"', block)
                self.assertIn(
                    'if ! TERMINAL_RECEIPT_SHA=$(git log -1 --format=%H '
                    '"$BASE_SHA" -- ledger/receipts/batches); then',
                    block,
                )
                self.assertIn(
                    'if [[ ! "$TERMINAL_RECEIPT_SHA" =~ ^[0-9a-f]{40}$ ]]; then',
                    block,
                )
                self.assertIn(
                    'if ! resolved_terminal_receipt_sha=$(git rev-parse --verify '
                    '"$TERMINAL_RECEIPT_SHA^{commit}"); then',
                    block,
                )
                self.assertIn(
                    'if [[ "$resolved_terminal_receipt_sha" != "$TERMINAL_RECEIPT_SHA" ]]; then',
                    block,
                )
                self.assertIn(receipt_bound_delta, block)
                self.assertIn(current_main_route, block)
                self.assertIn(historical_main_route, block)
                self.assertNotIn("--canonical-base-sha", historical_main_route)
                terminal_parent_route = (
                    'if [[ "$TERMINAL_RECEIPT_SHA" == "$BASE_SHA" ]]; then\n'
                    '            if ! base_parent_line=$(git rev-list --parents -n 1 "$BASE_SHA"); then'
                )
                self.assertIn(terminal_parent_route, block)
                historical_terminal_route = (
                    'else\n'
                    '              (\n'
                    '                cd "$validation_root"\n'
                    '                args=(python scripts/validate_receipts.py --mode canonical-main '
                    '--authority-sha "$BASE_SHA" --validation-level source-replay)\n'
                    '                "${args[@]}"\n'
                    '              )\n'
                    '            fi'
                )
                self.assertIn(historical_terminal_route, block)
                self.assertIn(canonical_base_route, block)
                self.assertIn(
                    'validation_workspace=$(mktemp -d)\n'
                    '            validation_root="$validation_workspace/repository"\n'
                    '            validation_source=$(git rev-parse --show-toplevel)\n'
                    '            cleanup_canonical_base_workspace() {\n'
                    '              rm -rf -- "$validation_workspace" >/dev/null 2>&1 || true\n'
                    '            }\n'
                    '            trap cleanup_canonical_base_workspace EXIT\n'
                    '            if ! git clone --no-local --no-hardlinks --no-checkout "$validation_source" "$validation_root" >/dev/null 2>&1; then\n'
                    '              printf \'%s\\n\' \'Canonical base receipt validation workspace unavailable.\' >&2\n'
                    '              exit 1\n'
                    '            fi\n'
                    '            if ! git -C "$validation_root" checkout --detach "$BASE_SHA" >/dev/null 2>&1; then\n'
                    '              printf \'%s\\n\' \'Canonical base receipt validation workspace unavailable.\' >&2\n'
                    '              exit 1\n'
                    '            fi\n',
                    block,
                )
                self.assertEqual(2, block.count('cd "$validation_root"'))
                self.assertIn(
                    '            (\n'
                    '              cd "$validation_root"\n'
                    f'              {canonical_base_route}\n'
                    '              "${args[@]}"\n'
                    '            )',
                    block,
                )
                self.assertIn(strict_pr_route, block)
                self.assertLess(block.index(canonical_base_route), block.index(strict_pr_route))
                self.assertIn("fetch-depth: 0", workflow)
                self.assertIn("Direct controller evaluation append route is retired", block)
                self.assertIn(
                    'expected=$(printf \'%s\\n\' .github/workflows/ci.yml .github/workflows/public-safety.yml tests/test_controller_maintenance.py | sort)',
                    block,
                )
                self.assertNotIn(
                    'test -z "$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- ledger/receipts/batches)"',
                    block,
                )
                self.assertNotIn("continue-on-error", block)
        self.assertEqual(blocks[0], blocks[1])


    def test_code_only_main_push_selects_canonical_main_and_not_legacy(self):
        with tempfile.TemporaryDirectory(prefix="ledger-code-only-main-push-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            base_sha = commit_blob(root, "source.py", b"base\n", "base")
            head_sha = commit_blob(root, "source.py", b"base\ncode-only\n", "code-only")

            for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                with self.subTest(workflow=relative):
                    result = self._run_push_route(workflow, root, base_sha, head_sha)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("route_completed", result.stdout)
                    self.assertIn("legacy_context=false", result.stdout)
                    self.assertIn("canonical_main_context=false", result.stdout)
                    self.assertIn("canonical_main_historical_context=true", result.stdout)
                    self.assertIn("canonical_base_context=false", result.stdout)
                    self.assertIn(
                        'args=(python scripts/validate_receipts.py --mode canonical-main '
                        '--authority-sha "$HEAD_SHA" --validation-level source-replay)',
                        self._receipt_route_block(workflow),
                    )


    def test_supported_four_file_main_push_selects_historical_canonical_main(self):
        paths = (
            "evaluations.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        )
        with tempfile.TemporaryDirectory(prefix="ledger-four-file-main-push-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"before\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            base_sha = git(root, "rev-parse", "HEAD")
            for path in paths:
                (root / path).write_bytes(b"after\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "four-file evaluation")
            head_sha = git(root, "rev-parse", "HEAD")
            actual_paths = git(root, "diff", "--name-only", base_sha, head_sha).splitlines()
            self.assertTrue(all(actual_paths))
            self.assertEqual(len(actual_paths), len(set(actual_paths)))
            self.assertEqual(set(paths), set(actual_paths))
            order_file = root / "diff-order.txt"
            order_file.write_bytes(
                b"scorecard.md\n"
                b"README.md\n"
                b"evaluations.jsonl\n"
                b"analysis/model-recommendation.json\n"
            )
            git(root, "config", "diff.orderFile", str(order_file))
            hostile_paths = git(
                root, "diff", "--name-only", base_sha, head_sha
            ).splitlines()
            self.assertEqual(
                [
                    "scorecard.md",
                    "README.md",
                    "evaluations.jsonl",
                    "analysis/model-recommendation.json",
                ],
                hostile_paths,
            )
            self.assertTrue(all(hostile_paths))
            self.assertEqual(len(hostile_paths), len(set(hostile_paths)))
            self.assertEqual(set(paths), set(hostile_paths))

            for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                with self.subTest(workflow=relative):
                    result = self._run_push_route(workflow, root, base_sha, head_sha)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("route_completed", result.stdout)
                    self.assertIn("legacy_context=false", result.stdout)
                    self.assertIn("canonical_main_context=false", result.stdout)
                    self.assertIn("canonical_main_historical_context=true", result.stdout)
                    self.assertIn("canonical_base_context=false", result.stdout)
                    self.assertIn(
                        'args=(python scripts/validate_receipts.py --mode canonical-main '
                        '--authority-sha "$HEAD_SHA" --validation-level source-replay)',
                        self._receipt_route_block(workflow),
                    )

    def test_supported_four_file_missing_path_fails_closed(self):
        paths = (
            "evaluations.jsonl",
            "README.md",
            "scorecard.md",
        )
        with tempfile.TemporaryDirectory(prefix="ledger-four-file-missing-main-push-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"before\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            base_sha = git(root, "rev-parse", "HEAD")
            for path in paths:
                (root / path).write_bytes(b"after\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "four-file evaluation missing one output")
            head_sha = git(root, "rev-parse", "HEAD")
            actual_paths = git(
                root, "diff", "--name-only", base_sha, head_sha
            ).splitlines()
            self.assertNotEqual(
                set(actual_paths),
                {
                    "evaluations.jsonl",
                    "README.md",
                    "scorecard.md",
                    "analysis/model-recommendation.json",
                },
            )
            for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                with self.subTest(workflow=relative):
                    result = self._run_push_route(workflow, root, base_sha, head_sha)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(
                        "Canonical receipt-bound data changed without a receipt.",
                        result.stderr,
                    )
                    self.assertNotIn("route_completed", result.stdout)

    def test_supported_four_file_plus_unrelated_file_fails_closed(self):
        paths = (
            "evaluations.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
            "unrelated.txt",
        )
        with tempfile.TemporaryDirectory(prefix="ledger-four-file-plus-one-main-push-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"before\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            base_sha = git(root, "rev-parse", "HEAD")
            for path in paths:
                (root / path).write_bytes(b"after\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "four-file evaluation plus unrelated")
            head_sha = git(root, "rev-parse", "HEAD")

            for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                with self.subTest(workflow=relative):
                    result = self._run_push_route(workflow, root, base_sha, head_sha)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(
                        "Canonical receipt-bound data changed without a receipt.",
                        result.stderr,
                    )
                    self.assertNotIn("route_completed", result.stdout)

    def test_receipt_bound_main_change_without_receipt_fails_closed_for_each_path(self):
        bound_paths = (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        )
        for path in bound_paths:
            with tempfile.TemporaryDirectory(prefix="ledger-bound-main-push-") as temp_raw:
                root = Path(temp_raw)
                init_fixture_repo(root)
                base_sha = commit_blob(root, path, b"before\n", "base")
                head_sha = commit_blob(root, path, b"after\n", "bound change")

                for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                    workflow = (ROOT / relative).read_text(encoding="utf-8")
                    block = self._receipt_route_block(workflow)
                    with self.subTest(path=path, workflow=relative):
                        result = self._run_push_route(workflow, root, base_sha, head_sha)
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(
                            "Canonical receipt-bound data changed without a receipt.",
                            result.stderr,
                        )
                        self.assertNotIn("route_completed", result.stdout)
                        guard_index = block.index(
                            "Canonical receipt-bound data changed without a receipt."
                        )
                        validator_index = block.index("python scripts/validate_receipts.py")
                        self.assertLess(guard_index, validator_index)

    def test_receipt_changing_main_push_selects_canonical_main_with_head_and_base(self):
        with tempfile.TemporaryDirectory(prefix="ledger-receipt-main-push-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            receipt = "ledger/receipts/batches/terminal.json"
            base_sha = commit_blob(root, receipt, b"before\n", "base receipt")
            head_sha = commit_blob(root, receipt, b"after\n", "receipt change")

            for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                block = self._receipt_route_block(workflow)
                with self.subTest(workflow=relative):
                    result = self._run_push_route(workflow, root, base_sha, head_sha)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("route_completed", result.stdout)
                    self.assertIn("legacy_context=false", result.stdout)
                    self.assertIn("canonical_main_context=true", result.stdout)
                    self.assertIn("canonical_main_historical_context=false", result.stdout)
                    self.assertIn("canonical_base_context=false", result.stdout)
                    self.assertIn(
                        'args=(python scripts/validate_receipts.py --mode canonical-main '
                        '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
                        '--validation-level source-replay)',
                        block,
                    )

    def test_code_only_main_push_canonical_main_validates_historical_terminal_seal(self):
        authority_sha = "3fc9066246f3de23c832ec938baf0cf09f2af4a8"
        base_sha = "be69246a7b9e7f06601f1e6ed032202a5e8a0b1f"
        self.assertEqual(
            "",
            git(ROOT, "diff", "--name-only", base_sha, authority_sha, "--", "ledger/receipts/batches"),
        )
        self.assertEqual(
            "",
            git(
                ROOT,
                "diff",
                "--name-only",
                base_sha,
                authority_sha,
                "--",
                "evaluations.jsonl",
                "ledger/dispositions.jsonl",
                "README.md",
                "scorecard.md",
                "analysis/model-recommendation.json",
            ),
        )
        terminal_receipt_sha = git(
            ROOT,
            "log",
            "-1",
            "--format=%H",
            authority_sha,
            "--",
            "ledger/receipts/batches",
        )
        self.assertNotEqual(authority_sha, terminal_receipt_sha)

        validation_environment = os.environ.copy()
        validation_environment.pop("GH_TOKEN", None)
        validation_environment.pop("GITHUB_TOKEN", None)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/validate_receipts.py",
                "--mode",
                "canonical-main",
                "--authority-sha",
                authority_sha,
                "--validation-level",
                "structural",
            ],
            cwd=ROOT,
            env=validation_environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

        self.assertIn("Batch receipt structural validation passed", result.stdout)
        historical_route = (
            'args=(python scripts/validate_receipts.py --mode canonical-main '
            '--authority-sha "$HEAD_SHA" --validation-level source-replay)'
        )
        current_route = (
            'args=(python scripts/validate_receipts.py --mode canonical-main '
            '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
            '--validation-level source-replay)'
        )
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            block = self._receipt_route_block(workflow)
            with self.subTest(workflow=relative):
                self.assertIn(historical_route, block)
                self.assertNotIn("--canonical-base-sha", historical_route)
                self.assertIn(current_route, block)

    def test_controller_evaluation_route_is_fail_closed(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/evaluation-*', workflow)
                self.assertIn("Direct controller evaluation append route is retired", workflow)
                self.assertNotIn(".controller-evaluation-intake.json", workflow)

    def test_controller_maintenance_scope_is_exact_three_files(self):
        required = {
            ".github/workflows/ci.yml",
            ".github/workflows/public-safety.yml",
            "tests/test_controller_maintenance.py",
        }
        forbidden = {"scripts/validate_receipts.py"}
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/ledger-maintenance-*', workflow)
                self.assertIn('git diff --name-only "$BASE_SHA" "$HEAD_SHA"', workflow)
                self.assertIn("legacy_context=true", workflow)
                for path in required:
                    self.assertIn(path, workflow)
                for path in forbidden:
                    self.assertNotIn(f"{path} | sort)", workflow)

    def test_ci_does_not_contain_direct_controller_transport(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("append-controller-evaluation:", workflow)
        self.assertNotIn(".controller-evaluation-intake.json", workflow)
        self.assertNotIn("git push origin HEAD:${TARGET_BRANCH}", workflow)
        self.assertIn("Direct controller evaluation append route is retired", workflow)

    def test_retired_transport_has_no_intake_contract(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertNotIn('= ".controller-evaluation-intake.json"', workflow)
        self.assertNotIn("intake_path.unlink()", workflow)

    def test_direct_evaluation_delta_is_rejected_before_suite_selection(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('"$HEAD_REF" == controller/evaluation-*', workflow)
                self.assertIn("Direct controller evaluation append route is retired", workflow)
                self.assertNotIn("data_only_evaluation", workflow)

    def test_retired_transport_has_no_commit_or_push_side_effect(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("git commit -m 'Append controller evaluation'", workflow)
        self.assertNotIn("git push origin HEAD:${TARGET_BRANCH}", workflow)
        self.assertNotIn("Validate and append public-safe evaluation", workflow)

    def test_main_push_requires_frozen_receipt_bytes_unchanged(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(
                'git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- ledger/receipts/batches',
                workflow,
            )

    def test_maintenance_lane_still_runs_complete_suite(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("GITHUB_EVENT_NAME=push GITHUB_REF_NAME=main python -m unittest discover", workflow)
            self.assertIn("controller/ledger-maintenance-*", workflow)

    def test_luna_controller_evaluation_reaches_generated_views(self):
        records = rebuild_views.load_records()
        source = next(
            copy.deepcopy(record)
            for record in reversed(records)
            if record.get("record_type") == "evaluation"
        )
        source["run_id"] = "controller-luna-view-generation-probe"
        source["provider"] = "OpenAI"
        source["model"] = "GPT-5.6 Luna"
        source["reviewed_at"] = "2026-08-11T00:00:00Z"
        source["subject_alias"] = "controller-luna-schema-probe"
        source["revision_binding"] = "non-identifying-controller-luna-schema-probe"

        evaluations = rebuild_views.resolved_evaluations([*records, source])
        readme, scorecard, recommendation = rebuild_views.expected_files(evaluations)

        self.assertIn("GPT-5.6 Luna", readme)
        self.assertIn("GPT-5.6 Luna", scorecard)
        self.assertIn("GPT-5.6 Luna", json.dumps(recommendation, sort_keys=True))

    def test_luna_execution_setting_identities_are_rejected_by_public_safety(self):
        model_words = ("GPT", "5", "6", "Luna")
        for execution_setting in ("Medium", "High", "Max"):
            ordinary = (
                "-".join(model_words[:2])
                + "."
                + model_words[2]
                + " "
                + model_words[3]
                + " "
                + execution_setting
            )
            fullwidth = "".join(
                chr(ord(character) + 0xFEE0)
                if "!" <= character <= "~"
                else character
                for character in ordinary
            )
            em_dash = chr(0x2014).join((*model_words, execution_setting))
            for identity in (ordinary, fullwidth, em_dash):
                with self.subTest(setting=execution_setting, identity=repr(identity)):
                    failures = public_safety.scan_public_text("probe", identity)
                    self.assertTrue(
                        failures,
                        "Luna execution-setting identity must fail closed",
                    )

    def test_luna_rule_manifest_seals_all_prospective_rules(self):
        manifest_path = ROOT / "migrations" / "luna-execution-setting-history-activation.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest),
            {"schema_version", "manifest_type", "rule_count", "rule_set_sha256"},
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["manifest_type"],
            "luna_execution_setting_history_activation",
        )
        self.assertEqual(manifest["rule_count"], 3)
        self.assertEqual(len(public_safety.LUNA_EXECUTION_SETTING_RULES), 3)
        expected_hash = "50cf6f4f49f8b43876ef07fa88bda745d9c0b2cbcf1359a60eead3baa8a68bb5"
        self.assertEqual(manifest["rule_set_sha256"], expected_hash)
        self.assertEqual(
            luna_rule_set_sha256(public_safety.LUNA_EXECUTION_SETTING_RULES),
            expected_hash,
        )
        weakened = public_safety.LUNA_EXECUTION_SETTING_RULES[:-1]
        self.assertNotEqual(luna_rule_set_sha256(weakened), expected_hash)

    def test_luna_tdd_history_exceptions_are_exact(self):
        self.assertEqual(
            public_safety.LUNA_TDD_HISTORY_ALLOWED_MATCHES,
            frozenset(
                {
                    (
                        "ba224fb72dd9e10fd65d36fdbd33f2974679f8ce",
                        "tests/test_controller_maintenance.py",
                        270,
                        "luna_execution_setting_003",
                    ),
                    (
                        "6e0ec65979831e720680d0c7633ec9c427e2cceb",
                        "tests/test_controller_maintenance.py",
                        242,
                        "luna_execution_setting_003",
                    ),
                }
            ),
        )

    def test_luna_history_rejects_identity_split_across_contiguous_added_lines(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-added-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed safe history")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "add split identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_luna_history_rejects_added_line_with_unchanged_neighbor_context(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-context-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed setting fragment")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "add neighbouring model fragment")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_luna_history_ignores_unrelated_preexisting_identity(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-existing-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                model_line + "\n" + setting_line + "\nsafe\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed existing identity")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                model_line + "\n" + setting_line + "\nsafe changed\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "change unrelated context")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertEqual([], failures)

    def test_luna_history_detects_deletion_only_introduction(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-delete-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                model_line + "\nseparator\n" + setting_line + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed separated fragments")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(model_line + "\n" + setting_line + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "delete separator only")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove introduced identity")

            failures = public_safety.luna_history_failures_in_range(start, root=root)

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_luna_history_rejects_relocated_occurrence_with_equal_count(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-relocation-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed grandfathered occurrence")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "header\nsafe middle\nfooter\n"
                + model_line
                + "\n"
                + setting_line
                + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "relocate occurrence without changing count")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove relocated occurrence")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_luna_history_allows_continuously_inherited_line_shifts(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting_line = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-line-shift-history-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            history = root / "history.txt"
            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed inherited occurrence")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "header\nunrelated insertion\n"
                + model_line
                + "\n"
                + setting_line
                + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "shift occurrence down")

            history.write_text(
                "header\n" + model_line + "\n" + setting_line + "\nfooter\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove unrelated insertion")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertEqual([], failures)

    def test_oversized_jsonl_still_rejects_luna_execution_setting(self):
        model_line = "-".join(("GPT", "5")) + "." + "6"
        setting = " ".join(("Luna", "Max"))
        identity = model_line + " " + setting
        with tempfile.TemporaryDirectory(prefix="ledger-large-jsonl-") as temp_raw:
            root = Path(temp_raw)
            path = root / "evaluations.jsonl"
            record = {
                "note": "x" * (public_safety.MAX_TEXT_BYTES + 64) + " " + identity,
            }
            path.write_text(
                json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_jsonl_object_keys_are_scanned_in_live_and_history(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        identity = model_fragment + " " + setting_fragment

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-key-context-") as temp_raw:
            root = Path(temp_raw)
            complete_key = root / "complete.jsonl"
            complete_key.write_text(
                json.dumps({identity: "safe"}) + "\n",
                encoding="utf-8",
            )
            complete_failures = public_safety.scan_jsonl(complete_key, root=root)
            self.assertTrue(
                any("luna_execution_setting" in failure for failure in complete_failures),
                complete_failures,
            )

            split_context = root / "split.jsonl"
            split_context.write_text(
                json.dumps({model_fragment: setting_fragment}) + "\n",
                encoding="utf-8",
            )
            split_failures = public_safety.scan_jsonl(split_context, root=root)
            self.assertTrue(
                any("luna_execution_setting" in failure for failure in split_failures),
                split_failures,
            )

            safe_keys = root / "safe.jsonl"
            safe_keys.write_text(
                json.dumps({"safe-key": "safe-value"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual([], public_safety.scan_jsonl(safe_keys, root=root))

            sensitive_key = root / "sensitive.jsonl"
            sensitive_key.write_text(
                json.dumps({"repository": "safe"}) + "\n",
                encoding="utf-8",
            )
            sensitive_failures = public_safety.scan_jsonl(sensitive_key, root=root)
            self.assertTrue(
                any("forbidden JSON key" in failure for failure in sensitive_failures),
                sensitive_failures,
            )

            history = root / "evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "seed safe JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                json.dumps({identity: "safe"}) + "\n",
                encoding="utf-8",
            )
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "introduce transient key identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "remove transient key identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_jsonl_cross_record_value_to_value_luna_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-cross-value-") as temp_raw:
            root = Path(temp_raw)
            path = root / "values.jsonl"
            path.write_text(
                json.dumps({"note": model_fragment})
                + "\n"
                + json.dumps({"note": setting_fragment})
                + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any(
                "values.jsonl:2" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_jsonl_cross_record_value_to_object_key_luna_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-cross-key-") as temp_raw:
            root = Path(temp_raw)
            path = root / "keys.jsonl"
            path.write_text(
                json.dumps({"note": model_fragment})
                + "\n"
                + json.dumps({setting_fragment: "safe"})
                + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any(
                "keys.jsonl:2" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_luna_history_rejects_transient_cross_record_identity(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-luna-cross-history-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            history = root / "evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "seed safe JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                json.dumps({"note": model_fragment})
                + "\n"
                + json.dumps({"note": setting_fragment})
                + "\n",
                encoding="utf-8",
            )
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "introduce transient cross-record identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "remove transient cross-record identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure
                and "evaluations.jsonl" in failure
                and "line-1" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_jsonl_cross_record_intervening_token_is_not_a_luna_identity(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-cross-negative-") as temp_raw:
            root = Path(temp_raw)
            path = root / "negative.jsonl"
            path.write_text(
                json.dumps({"note": model_fragment})
                + "\n"
                + json.dumps({"note": "Luna interposed"})
                + "\n"
                + json.dumps({"note": setting_fragment})
                + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertFalse(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_oversized_jsonl_cross_record_luna_identity_is_streamed(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-cross-oversized-") as temp_raw:
            root = Path(temp_raw)
            path = root / "oversized.jsonl"
            with path.open("wb") as handle:
                handle.write(
                    (
                        json.dumps(
                            {
                                "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
                                "note": model_fragment,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                handle.write(
                    (
                        json.dumps({"note": setting_fragment}, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                )
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any(
                "oversized.jsonl:2" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_amendment_103_three_record_current_tree_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-three-record-") as temp_raw:
            root = Path(temp_raw)
            path = root / "three-record.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps({"note": fragment})
                    for fragment in (model_fragment, "Luna", "Max")
                )
                + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any(
                "three-record.jsonl:3" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_amendment_103_three_record_history_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"

        with tempfile.TemporaryDirectory(prefix="ledger-luna-three-record-history-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            history = root / "evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "seed safe JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "\n".join(
                    json.dumps({"note": fragment})
                    for fragment in (model_fragment, "Luna", "Max")
                )
                + "\n",
                encoding="utf-8",
            )
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "introduce three-record identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "remove three-record identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure
                and "evaluations.jsonl" in failure
                and "line-1" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_amendment_103_intervening_token_blocks_three_record_identity(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-three-record-negative-") as temp_raw:
            root = Path(temp_raw)
            path = root / "three-record-negative.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps({"note": fragment})
                    for fragment in (model_fragment, "Luna", "interposed", "Max")
                )
                + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertFalse(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_amendment_103_numeric_scalar_current_tree_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5"))
        setting_fragment = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-numeric-scalar-") as temp_raw:
            root = Path(temp_raw)
            path = root / "numeric-scalar.jsonl"
            path.write_text(
                json.dumps([model_fragment, 6, setting_fragment]) + "\n",
                encoding="utf-8",
            )

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any("numeric-scalar.jsonl:1" in failure
                and "luna_execution_setting" in failure
                for failure in failures),
            failures,
        )

    def test_red_amendment_103_numeric_scalar_history_identity_is_rejected(self):
        model_fragment = "-".join(("GPT", "5"))
        setting_fragment = " ".join(("Luna", "Max"))
        with tempfile.TemporaryDirectory(prefix="ledger-luna-numeric-scalar-history-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            history = root / "evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "seed safe JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                json.dumps([model_fragment, 6, setting_fragment]) + "\n",
                encoding="utf-8",
            )
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "introduce numeric scalar identity")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "remove numeric scalar identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure
                and "evaluations.jsonl" in failure
                and "line-1" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_amendment_103_appended_safe_line_keeps_occurrence_inherited(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-luna-inherited-append-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            history = root / "history.txt"
            history.write_text(
                "header\n"
                + model_fragment
                + "\n"
                + setting_fragment
                + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed grandfathered occurrence")
            start = git(root, "rev-parse", "HEAD")

            history.write_text(
                "header\n"
                + model_fragment
                + "\n"
                + setting_fragment
                + "\n"
                + "safe appended line\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "append unrelated safe line")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertEqual([], failures)

    def test_red_amendment_103_gitattributes_cannot_hide_utf8_identity(self):
        model_fragment = "-".join(("GPT", "5")) + ".6"
        setting_fragment = " ".join(("Luna", "Max"))
        identity = model_fragment + " " + setting_fragment

        with tempfile.TemporaryDirectory(prefix="ledger-luna-gitattributes-") as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            history = root / "history.txt"
            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "seed safe history")
            start = git(root, "rev-parse", "HEAD")

            attributes = root / ".gitattributes"
            attributes.write_text("history.txt -diff\n", encoding="utf-8")
            git(root, "add", ".gitattributes")
            git(root, "commit", "-qm", "mark history path as no-diff")

            history.write_text(identity + "\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "introduce UTF8 identity under no-diff")
            introduced = git(root, "rev-parse", "HEAD")

            history.write_text("safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "remove UTF8 identity")
            end = git(root, "rev-parse", "HEAD")

            failures = public_safety.luna_history_failures_in_range(
                start,
                end=end,
                root=root,
            )

        self.assertTrue(
            any(
                introduced[:12] in failure
                and "history.txt" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )

    def test_red_amendment_103_oversized_scalar_boundary_is_streamed(self):
        model_fragment = "-".join(("GPT", "5"))
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-oversized-scalar-") as temp_raw:
            root = Path(temp_raw)
            path = root / "oversized-scalar.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
                        "note": model_fragment,
                    },
                    separators=(",", ":"),
                )
                + "\n"
                + json.dumps({"value": 6}, separators=(",", ":"))
                + "\n"
                + json.dumps({"note": setting_fragment}, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)

            failures = public_safety.scan_jsonl(path, root=root)

        self.assertTrue(
            any(
                "oversized-scalar.jsonl:3" in failure
                and "luna_execution_setting" in failure
                for failure in failures
            ),
            failures,
        )


    def test_main_context_never_leaks_into_fixture_repositories(self):
        actual_head = git(ROOT, "rev-parse", "HEAD")
        with mock.patch.dict(
            os.environ,
            {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"},
            clear=True,
        ):
            self.assertTrue(_running_on_canonical_main(ROOT, actual_head))

        with tempfile.TemporaryDirectory(prefix="ledger-main-context-") as temp_raw:
            root = Path(temp_raw)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            (root / "file.txt").write_text("one\n", encoding="utf-8")
            git(root, "add", "file.txt")
            git(root, "commit", "-qm", "one")
            head = git(root, "rev-parse", "HEAD")

            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertFalse(_running_on_canonical_main(root, head))
            with mock.patch.dict(
                os.environ,
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"},
                clear=True,
            ):
                self.assertFalse(_running_on_canonical_main(root, head))

    def test_red_jsonl_duplicate_keys_fail_live_oversized_and_historical(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        identity = model_fragment + " " + setting_fragment
        duplicate_record = (
            '{"note":'
            + json.dumps(identity)
            + ',"note":"safe"}\n'
        ).encode("utf-8")
        nested_duplicate_record = b'{"outer":{"safe":"one","safe":"two"}}\n'

        with tempfile.TemporaryDirectory(prefix="ledger-jsonl-duplicate-keys-") as temp_raw:
            root = Path(temp_raw)
            live = root / "live.jsonl"
            live.write_bytes(duplicate_record + nested_duplicate_record)
            live_failures = public_safety.scan_jsonl(live, root=root)
            self.assertEqual(
                2,
                sum("duplicate object keys" in failure for failure in live_failures),
                live_failures,
            )
            self.assertTrue(
                all(identity not in failure for failure in live_failures),
                live_failures,
            )

            oversized_root = root / "oversized"
            oversized_root.mkdir()
            oversized_record = (
                '{"padding":"'
                + ("x" * (public_safety.MAX_TEXT_BYTES + 64))
                + '","note":'
                + json.dumps(identity)
                + ',"note":"safe"}\n'
            ).encode("utf-8")
            oversized_path = oversized_root / "evaluations.jsonl"
            oversized_path.write_bytes(oversized_record)
            self.assertGreater(oversized_path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            oversized_failures = public_safety.tree_failures(oversized_root)
            self.assertTrue(
                any("duplicate object keys" in failure for failure in oversized_failures),
                oversized_failures,
            )

            history = root / "historical-evaluations.jsonl"
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "ledger-fixture")
            git(root, "config", "user.email", "fixture" + "@" + "example.invalid")
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "seed historical JSONL")
            start = git(root, "rev-parse", "HEAD")

            history.write_bytes(duplicate_record)
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "introduce duplicate JSONL key")
            history.write_text('{"note":"safe"}\n', encoding="utf-8")
            git(root, "add", "historical-evaluations.jsonl")
            git(root, "commit", "-qm", "remove duplicate JSONL key")
            end = git(root, "rev-parse", "HEAD")

            with self.assertRaisesRegex(RuntimeError, "invalid text") as context:
                public_safety.luna_history_failures_in_range(
                    start,
                    end=end,
                    root=root,
                )

        self.assertNotIn(identity, str(context.exception))

    def test_legacy_receipt_authority_is_exact_public_pr151_terminal(self):
        self.assertEqual(
            "2d4ec54c4a922ee37d0ae53a52a9c97732fb76d8",
            LEGACY_FROZEN_RECEIPT_AUTHORITY,
        )

    def test_receipt_changing_pull_request_mode_remains_strict(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            block = self._receipt_route_block(workflow)
            self.assertIn(
                'if [[ -z "$receipt_delta" && -z "$receipt_bound_delta" ]]; then',
                block,
            )
            self.assertIn(
                'args=(python scripts/validate_receipts.py --mode pr '
                '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
                '--validation-level source-replay)',
                block,
            )
            self.assertNotIn("continue-on-error", block)

    def test_receipt_bound_canonical_changes_prevent_canonical_base_handling(self):
        bound_paths = (
            "evaluations.jsonl",
            "ledger/dispositions.jsonl",
            "README.md",
            "scorecard.md",
            "analysis/model-recommendation.json",
        )
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            block = self._receipt_route_block(workflow)
            with self.subTest(workflow=relative):
                self.assertEqual(
                    2,
                    block.count(
                        'receipt_bound_delta=$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" '
                        '-- evaluations.jsonl ledger/dispositions.jsonl README.md scorecard.md '
                        'analysis/model-recommendation.json)'
                    ),
                )
                for path in bound_paths:
                    self.assertIn(path, block)
                self.assertIn(
                    'if [[ -z "$receipt_delta" && -z "$receipt_bound_delta" ]]; then',
                    block,
                )
                self.assertIn(
                    'args=(python scripts/validate_receipts.py --mode pr '
                    '--authority-sha "$HEAD_SHA" --canonical-base-sha "$BASE_SHA" '
                    '--validation-level source-replay)',
                    block,
                )

    def test_historical_terminal_receipt_allows_merge_base_without_synthetic_parent(self):
        for relative in (".github/workflows/ci.yml", ".github/workflows/public-safety.yml"):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            block = self._receipt_route_block(workflow)
            historical_route = (
                'else\n'
                '              (\n'
                '                cd "$validation_root"\n'
                '                args=(python scripts/validate_receipts.py --mode canonical-main '
                '--authority-sha "$BASE_SHA" --validation-level source-replay)\n'
                '                "${args[@]}"\n'
                '              )\n'
                '            fi'
            )
            with self.subTest(workflow=relative):
                self.assertIn('if [[ "$TERMINAL_RECEIPT_SHA" == "$BASE_SHA" ]]; then', block)
                self.assertIn(historical_route, block)
                self.assertNotIn("--canonical-base-sha", historical_route)


    def test_red_oversized_jsonl_preserves_cross_value_luna_context(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        record = {
            "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
            "parts": [model_fragment, setting_fragment],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "evaluations.jsonl"
            jsonl.write_text(json.dumps(record) + "\n", encoding="utf-8")
            self.assertGreater(jsonl.stat().st_size, public_safety.MAX_TEXT_BYTES)

            failures = public_safety.tree_failures(root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_luna_history_merge_only_introduction_is_not_missed(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            history = root / "history.txt"
            history.write_text("base-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            git(root, "checkout", "-qb", "feature")
            history.write_text("feature-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "feature")

            git(root, "checkout", "-q", "main")
            history.write_text("main-safe\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "main divergence")

            merge_result = subprocess.run(
                ["git", "merge", "--no-ff", "--no-commit", "feature"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(merge_result.returncode, 0)
            history.write_text(
                model_fragment + "\n" + setting_fragment + "\n",
                encoding="utf-8",
            )
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "merge resolution")
            introduced = git(root, "rev-parse", "HEAD").strip()
            parents = git(root, "show", "-s", "--format=%P", introduced).split()
            self.assertEqual(len(parents), 2)

            history.write_text("safe-after-delete\n", encoding="utf-8")
            git(root, "add", "history.txt")
            git(root, "commit", "-qm", "delete transient identity")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertTrue(
            any(introduced[:12] in failure and "luna_execution_setting" in failure for failure in failures),
            failures,
        )

    def test_red_safe_oversized_jsonl_history_is_processed_incrementally(self):
        safe_record = {"note": "x" * (public_safety.MAX_TEXT_BYTES + 64)}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            jsonl = root / "evaluations.jsonl"
            jsonl.write_text('{"note":"base-safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe_record) + "\n")
            self.assertGreater(jsonl.stat().st_size, public_safety.MAX_TEXT_BYTES)
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "safe oversized append")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertEqual([], failures)

    def test_red_oversized_non_root_jsonl_luna_identity_is_scanned(self):
        model = '-'.join(('GPT', '5')) + '.6'
        setting = ' '.join(('Luna', 'Max'))
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, (
                json.dumps({'padding': 'x' * (public_safety.MAX_TEXT_BYTES + 64),
                            'note': model + ' ' + setting}, separators=(',', ':'))
                + '\n'
            ).encode('utf-8'))
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertTrue(any('luna_execution_setting' in x for x in failures), failures)

    def test_red_oversized_non_root_jsonl_cross_value_identity_is_scanned(self):
        model = '-'.join(('GPT', '5')) + '.6'
        setting = ' '.join(('Luna', 'Max'))
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, (
                json.dumps({'padding': 'x' * (public_safety.MAX_TEXT_BYTES + 64),
                            'parts': [model, setting]}, separators=(',', ':'))
                + '\n'
            ).encode('utf-8'))
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertTrue(any('luna_execution_setting' in x for x in failures), failures)

    def test_red_oversized_non_root_jsonl_object_key_is_scanned(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, (
                json.dumps({'padding': 'x' * (public_safety.MAX_TEXT_BYTES + 64),
                            luna_identity(): 'safe'}, separators=(',', ':'))
                + '\n'
            ).encode('utf-8'))
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertTrue(any('luna_execution_setting' in x for x in failures), failures)

    def test_red_oversized_non_root_jsonl_duplicate_key_fails_closed(self):
        q = chr(34)
        raw = (
            '{' + q + 'padding' + q + ':' + q
            + ('x' * (public_safety.MAX_TEXT_BYTES + 64)) + q + ','
            + q + 'note' + q + ':' + json.dumps(luna_identity()) + ','
            + q + 'note' + q + ':' + q + 'safe' + q + '}\n'
        ).encode('utf-8')
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, raw)
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertTrue(any('duplicate object keys' in x for x in failures), failures)
        self.assertTrue(all(luna_identity() not in x for x in failures), failures)

    def test_red_oversized_non_root_jsonl_sensitive_key_is_scanned(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, (
                json.dumps({'padding': 'x' * (public_safety.MAX_TEXT_BYTES + 64),
                            'repository': 'safe'}, separators=(',', ':'))
                + '\n'
            ).encode('utf-8'))
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertTrue(any('forbidden JSON key' in x for x in failures), failures)

    def test_red_safe_oversized_non_root_jsonl_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            candidate = nested_candidate_tree(Path(temp_raw))
            path = write_candidate_jsonl(candidate, (
                json.dumps({'padding': 'x' * (public_safety.MAX_TEXT_BYTES + 64),
                            'note': 'safe'}, separators=(',', ':'))
                + '\n'
            ).encode('utf-8'))
            self.assertGreater(path.stat().st_size, public_safety.MAX_TEXT_BYTES)
            failures = public_safety.tree_failures(candidate)
        self.assertEqual([], failures)

    def test_red_luna_history_allows_binary_addition(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'seed.txt', b'safe\n', 'seed safe history')
            end = commit_blob(root, 'assets/image.bin', b'asset\x00', 'add binary asset')
            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)
        self.assertEqual([], failures)

    def test_red_luna_history_allows_binary_modification(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'assets/image.bin', b'asset-v1\x00', 'seed binary asset')
            end = commit_blob(root, 'assets/image.bin', b'asset-v2\x00', 'modify binary asset')
            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)
        self.assertEqual([], failures)

    def test_red_luna_history_allows_binary_deletion(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'assets/image.bin', b'asset\x00', 'seed binary asset')
            end = commit_delete(root, 'assets/image.bin', 'delete binary asset')
            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)
        self.assertEqual([], failures)

    def test_red_luna_history_detects_binary_to_prohibited_text(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'assets/image.bin', b'asset\x00', 'seed binary asset')
            end = commit_blob(root, 'assets/image.bin', (luna_identity() + '\n').encode('utf-8'), 'replace binary with prohibited text')
            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)
        self.assertTrue(any(end[:12] in x and 'luna_execution_setting' in x for x in failures), failures)

    def test_red_luna_history_allows_binary_to_safe_text(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'assets/image.bin', b'asset\x00', 'seed binary asset')
            end = commit_blob(root, 'assets/image.bin', b'safe text\n', 'replace binary with safe text')
            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)
        self.assertEqual([], failures)

    def test_red_luna_history_rejects_invalid_utf8_non_jsonl_text(self):
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'assets/text.bin', b'safe\n', 'seed text history')
            end = commit_blob(root, 'assets/text.bin', b'safe\xff\n', 'introduce invalid utf8')
            with self.assertRaisesRegex(RuntimeError, 'strict UTF-8'):
                public_safety.luna_history_failures_in_range(start, end=end, root=root)

    def test_red_luna_history_rejects_nul_containing_jsonl(self):
        q = bytes([34])
        nul_jsonl = b'{' + q + b'note' + q + b':' + q + b'bad' + b'\x00' + b'text' + q + b'}\n'
        with tempfile.TemporaryDirectory() as temp_raw:
            root = Path(temp_raw)
            init_fixture_repo(root)
            start = commit_blob(root, 'ledger/dispositions.jsonl', b'{' + q + b'note' + q + b':' + q + b'safe' + q + b'}\n', 'seed safe jsonl')
            end = commit_blob(root, 'ledger/dispositions.jsonl', nul_jsonl, 'introduce nul jsonl')
            with self.assertRaisesRegex(RuntimeError, 'invalid text'):
                public_safety.luna_history_failures_in_range(start, end=end, root=root)

    def test_red_unsafe_oversized_jsonl_history_remains_detectable(self):
        model_fragment = "-".join(("GPT", "5")) + "." + "6"
        setting_fragment = " ".join(("Luna", "Max"))
        unsafe_record = {
            "padding": "x" * (public_safety.MAX_TEXT_BYTES + 64),
            "parts": [model_fragment, setting_fragment],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "test" + "@" + "example.invalid")
            git(root, "config", "user.name", "Amendment Test")

            jsonl = root / "evaluations.jsonl"
            jsonl.write_text('{"note":"base-safe"}\n', encoding="utf-8")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "base")
            start = git(root, "rev-parse", "HEAD").strip()

            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(unsafe_record) + "\n")
            git(root, "add", "evaluations.jsonl")
            git(root, "commit", "-qm", "unsafe oversized append")
            end = git(root, "rev-parse", "HEAD").strip()

            failures = public_safety.luna_history_failures_in_range(start, end=end, root=root)

        self.assertTrue(
            any("luna_execution_setting" in failure for failure in failures),
            failures,
        )


if __name__ == "__main__":
    unittest.main()
