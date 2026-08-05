#!/usr/bin/env python3
"""Resolve and verify immutable workflow checkout and base authorities."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40


class WorkflowAuthorityError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowAuthorityError("workflow_authority_unavailable")
    return result.stdout.strip()


def _required_sha(value: str) -> str:
    if FULL_SHA.fullmatch(value) is None:
        raise WorkflowAuthorityError("workflow_authority_invalid")
    return value


def _commit(root: Path, value: str) -> str:
    value = _required_sha(value)
    resolved = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
    if resolved != value:
        raise WorkflowAuthorityError("workflow_authority_unavailable")
    return value


def _parents(root: Path, value: str) -> list[str]:
    fields = _git(root, "rev-list", "--parents", "-n", "1", value).split()
    if not fields or fields[0] != value:
        raise WorkflowAuthorityError("workflow_authority_unavailable")
    return fields[1:]


def _require_ancestor(root: Path, base_sha: str, head_sha: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowAuthorityError("workflow_base_not_ancestor")


def resolve_authority(
    root: Path,
    *,
    event_name: str,
    github_sha: str,
    checkout_sha: str,
    pr_head_sha: str = "",
    pr_base_sha: str = "",
    before_sha: str = "",
    dispatch_base_sha: str = "",
) -> dict[str, str]:
    checked_out = _commit(root, checkout_sha)
    if _git(root, "rev-parse", "HEAD") != checked_out:
        raise WorkflowAuthorityError("workflow_checkout_mismatch")

    if event_name == "pull_request":
        head_sha = _commit(root, pr_head_sha)
        base_sha = _commit(root, pr_base_sha)
        event_sha = _required_sha(github_sha)
        if event_sha in {head_sha, base_sha}:
            raise WorkflowAuthorityError("workflow_pr_event_authority_contradictory")
    elif event_name == "push":
        head_sha = _commit(root, github_sha)
        if before_sha == ZERO_SHA:
            parents = _parents(root, head_sha)
            if len(parents) != 1:
                raise WorkflowAuthorityError("workflow_zero_before_base_unavailable")
            base_sha = _commit(root, parents[0])
        else:
            base_sha = _commit(root, before_sha)
    elif event_name == "workflow_dispatch":
        head_sha = _commit(root, github_sha)
        base_sha = _commit(root, dispatch_base_sha)
    else:
        raise WorkflowAuthorityError("workflow_event_unsupported")

    if checked_out != head_sha:
        raise WorkflowAuthorityError("workflow_checkout_mismatch")
    _require_ancestor(root, base_sha, head_sha)
    return {"head_sha": head_sha, "base_sha": base_sha}


def parse_cli(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="resolve_workflow_authority")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--pr-head-sha", default="")
    parser.add_argument("--pr-base-sha", default="")
    parser.add_argument("--before-sha", default="")
    parser.add_argument("--dispatch-base-sha", default="")
    parser.add_argument("--output-file", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_cli(argv)
    try:
        evidence = resolve_authority(
            args.repository_root,
            event_name=args.event_name,
            github_sha=args.github_sha,
            checkout_sha=args.checkout_sha,
            pr_head_sha=args.pr_head_sha,
            pr_base_sha=args.pr_base_sha,
            before_sha=args.before_sha,
            dispatch_base_sha=args.dispatch_base_sha,
        )
        if args.output_file is not None:
            with args.output_file.open("a", encoding="utf-8", newline="\n") as output:
                output.write(f"head_sha={evidence['head_sha']}\n")
                output.write(f"base_sha={evidence['base_sha']}\n")
            print(
                "Verified immutable workflow authority: "
                f"HEAD={evidence['head_sha']} BASE={evidence['base_sha']}."
            )
        else:
            print(json.dumps(evidence, sort_keys=True))
    except (OSError, WorkflowAuthorityError):
        print("Workflow authority validation failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
