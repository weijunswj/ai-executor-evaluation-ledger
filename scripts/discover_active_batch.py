#!/usr/bin/env python3
"""Discover active (unfinished) scheduled-review batch branches on the remote."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

BATCH_BRANCH_RE = re.compile(
    r"^refs/heads/scheduled-review/batch-(?P<date>[0-9]{8})-(?P<seq>[0-9]{3})$"
)

TERMINAL_STATES = {"merged", "completed", "abandoned"}


def git_ls_remote_batches(remote: str = "origin") -> list[str]:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", remote, "refs/heads/scheduled-review/batch-*"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    refs: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            refs.append(parts[1])
    return refs


def parse_batch_branch(ref: str) -> tuple[str, str, str] | None:
    match = BATCH_BRANCH_RE.match(ref)
    if not match:
        return None
    return match.group(0), match.group("date"), match.group("seq")


def fetch_manifest_sha(remote: str, branch: str) -> str | None:
    manifest_path = branch.replace("refs/heads/", "") + ":scheduled-review/batches/"
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", remote + "/" + branch.replace("refs/heads/", "")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def is_batch_active(remote: str, branch: str) -> bool:
    branch_short = branch.replace("refs/heads/", "")
    manifest_ref = f"{remote}/{branch_short}:scheduled-review/batches/"
    try:
        result = subprocess.run(
            [
                "git", "cat-file", "-p",
                f"{remote}/{branch_short}:scheduled-review/batches/"
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        entries = result.stdout.strip().splitlines()
        batch_dirs = [e.split("\t")[1].rstrip("/") for e in entries if "\t" in e and e.split("\t")[1].endswith("/")]
        if not batch_dirs:
            return False
        for batch_dir in batch_dirs:
            manifest_file = f"{remote}/{branch_short}:scheduled-review/batches/{batch_dir}/manifest.json"
            manifest_result = subprocess.run(
                ["git", "cat-file", "-p", manifest_file],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if manifest_result.returncode != 0:
                continue
            manifest = json.loads(manifest_result.stdout)
            state = manifest.get("state", "")
            if state not in TERMINAL_STATES:
                return True
        return False
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return False


def discover(remote: str = "origin") -> dict[str, list[str]]:
    refs = git_ls_remote_batches(remote)
    active: list[str] = []
    malformed: list[str] = []
    terminal: list[str] = []

    for ref in refs:
        parsed = parse_batch_branch(ref)
        if parsed is None:
            malformed.append(ref)
        elif is_batch_active(remote, ref):
            active.append(ref)
        else:
            terminal.append(ref)

    return {"active": active, "malformed": malformed, "terminal": terminal}


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover active batch branches")
    parser.add_argument("--remote", default="origin", help="Remote name")
    args = parser.parse_args()

    try:
        result = discover(args.remote)
    except subprocess.CalledProcessError as exc:
        print(f"Git command failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))

    if result["malformed"]:
        print(f"Malformed refs: {len(result['malformed'])}", file=sys.stderr)
        return 1

    if len(result["active"]) > 1:
        print(f"Multiple active batches: {result['active']}", file=sys.stderr)
        return 1

    if result["active"]:
        print(f"Active batch: {result['active'][0]}")
    else:
        print("No active batch — new freeze permitted.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
