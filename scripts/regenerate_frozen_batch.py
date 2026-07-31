#!/usr/bin/env python3
"""Regenerate or verify the frozen batch through the production replay path."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.processor.batch_processor import (
    ProcessBatchConfig,
    build_batch_candidate,
)
from scripts.processor.common import (
    FROZEN_BATCH_ID,
    FROZEN_CANONICAL_BASE_SHA,
    ProcessorError,
    valid_git_sha,
)
from scripts.processor.transaction import replace_tracked_files


def _resolve_commit(root: Path, revision: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not valid_git_sha(value):
        raise ProcessorError("authority_missing")
    return value


def _policy_receipt(root: Path, authority_sha: str) -> dict:
    result = subprocess.run(
        [
            "git",
            "show",
            f"{authority_sha}:ledger/receipts/batches/{FROZEN_BATCH_ID}.json",
        ],
        cwd=root,
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        raise ProcessorError("authority_missing")
    try:
        value = json.loads(result.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError):
        raise ProcessorError("source_changed")
    if not isinstance(value, dict):
        raise ProcessorError("source_changed")
    return value


def build_candidate(
    root: Path,
    *,
    authority_sha: str,
    candidate_content_commit_sha: Optional[str] = None,
):
    authority_sha = _resolve_commit(root, authority_sha)
    receipt = _policy_receipt(root, authority_sha)
    if (
        receipt.get("base_sha") != FROZEN_CANONICAL_BASE_SHA
        or receipt.get("canonical_main_sha") != FROZEN_CANONICAL_BASE_SHA
    ):
        raise ProcessorError("processor_authority_mismatch")
    config = ProcessBatchConfig(
        operating_mode=receipt["batch_mode"],
        base_sha=FROZEN_CANONICAL_BASE_SHA,
        canonical_main_sha=FROZEN_CANONICAL_BASE_SHA,
        batch_id=FROZEN_BATCH_ID,
        controller_run_id=receipt["controller_run_id"],
        pr_number=receipt["pr_number"],
        expected_head_sha=authority_sha,
        activation_mode="dry-run",
        dry_run=True,
        source_issue_number=receipt["source_issue_number"],
        receipt_issue_number=receipt["receipt_issue_number"],
        repository_root=root,
        candidate_content_commit_sha=candidate_content_commit_sha,
    )
    return build_batch_candidate(config)


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="regenerate_frozen_batch")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--authority-sha", default="HEAD")
    parser.add_argument("--candidate-content-commit-sha")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        candidate_files, evidence = build_candidate(
            args.repository_root,
            authority_sha=args.authority_sha,
            candidate_content_commit_sha=args.candidate_content_commit_sha,
        )
        if args.write:
            replace_tracked_files(args.repository_root, candidate_files)
        else:
            for relative_path, expected in candidate_files.items():
                if (
                    args.repository_root / relative_path
                ).read_bytes() != expected:
                    raise ProcessorError("processor_integrity_failure")
    except (KeyError, OSError, RuntimeError, ProcessorError):
        print("Frozen batch regeneration failed.", file=sys.stderr)
        return 1
    action = "written" if args.write else "verified"
    print(
        "Frozen batch regeneration "
        f"{action}: {evidence['terminal_count']} outcomes, "
        f"{evidence['admitted_count']} admissions, "
        f"{evidence['later_comment_count']} later comments excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
