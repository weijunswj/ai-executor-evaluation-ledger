#!/usr/bin/env python3
"""Discover active scheduled-review batch branches via exact remote Git refs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BATCH_BRANCH_RE = re.compile(
    r"^refs/heads/scheduled-review/batch-(?P<date>[0-9]{8})-(?P<seq>[0-9]{3})$"
)
BATCH_ID_RE = re.compile(r"^BATCH-[0-9]{8}-[0-9]{3}$")

TERMINAL_STATES = {"merged", "completed", "abandoned"}


def git_ls_remote_batches(remote: str = "origin") -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", remote, "refs/heads/scheduled-review/batch-*"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    refs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            refs.append((parts[0], parts[1]))
    return refs


def parse_batch_branch(ref: str) -> tuple[str, str, str] | None:
    match = BATCH_BRANCH_RE.match(ref)
    if not match:
        return None
    return match.group(0), match.group("date"), match.group("seq")


def fetch_and_read_manifest(remote: str, sha: str, branch: str) -> dict[str, Any] | None:
    branch_short = branch.replace("refs/heads/", "")
    try:
        subprocess.run(
            ["git", "fetch", remote, f"{sha}:refs/tmp/batch-discovery"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return None

    try:
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", "-r", "refs/tmp/batch-discovery",
             "scheduled-review/batches/"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        _cleanup_tmp_ref()
        return None

    entries = result.stdout.strip().splitlines()
    batch_dirs = [e.split("\t")[-1].rstrip("/") for e in entries if "\t" in e and e.split("\t")[-1].endswith("/")]
    manifests_found: list[dict[str, Any]] = []

    for batch_dir in batch_dirs:
        parts = batch_dir.split("/")
        batch_id_candidate = parts[-1] if parts else ""
        if not BATCH_ID_RE.match(batch_id_candidate):
            continue
        manifest_path = f"scheduled-review/batches/{batch_id_candidate}/manifest.json"
        try:
            cat_result = subprocess.run(
                ["git", "cat-file", "-p", f"refs/tmp/batch-discovery:{manifest_path}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(cat_result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue

        expected_branch = f"scheduled-review/batch-{batch_id_candidate.split('-')[1]}-{batch_id_candidate.split('-')[2]}"
        if manifest.get("branch_name") != expected_branch:
            continue
        if manifest.get("batch_id") != batch_id_candidate:
            continue

        manifests_found.append(manifest)

    _cleanup_tmp_ref()

    if len(manifests_found) == 1:
        return manifests_found[0]
    return None


def _cleanup_tmp_ref() -> None:
    try:
        subprocess.run(
            ["git", "update-ref", "-d", "refs/tmp/batch-discovery"],
            cwd=ROOT,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        pass


def discover(remote: str = "origin") -> dict[str, Any]:
    refs = git_ls_remote_batches(remote)
    active: list[dict[str, Any]] = []
    malformed: list[str] = []
    terminal: list[str] = []

    for sha, ref in refs:
        parsed = parse_batch_branch(ref)
        if parsed is None:
            malformed.append(ref)
            continue

        manifest = fetch_and_read_manifest(remote, sha, ref)
        if manifest is None:
            malformed.append(f"{ref} (unreadable or malformed manifest)")
            continue

        branch_name = ref.replace("refs/heads/", "")
        if manifest.get("branch_name") != branch_name:
            malformed.append(f"{ref} (branch/manifest identity conflict)")
            continue

        if manifest.get("state", "") in TERMINAL_STATES:
            terminal.append(ref)
        else:
            active.append({"sha": sha, "ref": ref, "manifest": manifest})

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

    public = {
        "active_count": len(result["active"]),
        "malformed_count": len(result["malformed"]),
        "terminal_count": len(result["terminal"]),
    }
    print(json.dumps(public, indent=2))

    if result["malformed"]:
        for m in result["malformed"]:
            print(f"Malformed: {m}", file=sys.stderr)
        return 1

    if len(result["active"]) > 1:
        for a in result["active"]:
            print(f"Active conflict: {a['ref']} ({a['sha'][:12]})", file=sys.stderr)
        print("Multiple active batches — manual intervention required", file=sys.stderr)
        return 1

    if result["active"]:
        a = result["active"][0]
        print(f"Active batch: {a['manifest']['batch_id']} on {a['ref']} ({a['sha'][:12]})")
    else:
        print("No active batch — new freeze permitted.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
