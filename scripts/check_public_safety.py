#!/usr/bin/env python3
"""Fail closed when public ledger content contains secrets or identifying metadata."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = ROOT / ".public-safety-baseline"
MAX_TEXT_BYTES = 2_000_000

COMPANION_URL = "".join(
    (
        "https://github.com/",
        "weijunswj/",
        "Custom-Instruction-Framework-For-Web-based-LLMs/",
        "blob/main/CUSTOM_INSTRUCTIONS.md",
    )
)
COMPANION_LINK_LABEL = "LLM WEB CUSTOM INSTRUCTIONS SET"
COMPANION_README_LINE = (
    f"Used in conjunction with [{COMPANION_LINK_LABEL}]({COMPANION_URL})."
)
LEGACY_REVERSED_README_LINE = (
    f"Used in conjunction with [{COMPANION_URL}]({COMPANION_LINK_LABEL})."
)
LEGACY_SCRIPT_URL_LINE = f'        "{COMPANION_URL}",'
URL_MASK = "COMPANION_DOCUMENT_URL"

# These immutable commits already contain the URL after the fixed safety baseline.
# Bind each exception to the exact commit, file and complete added line so no future
# commit or other tracked location inherits the exception.
HISTORICAL_ALLOWED_LINES: dict[tuple[str, str], frozenset[str]] = {
    (
        "fc0c69d71d2e8ca28c8bcae0cf06f0010031377b",
        "README.md",
    ): frozenset({LEGACY_REVERSED_README_LINE}),
    (
        "674ac399e46b56d20f6f66a83b67d491f387f6af",
        "README.md",
    ): frozenset({LEGACY_REVERSED_README_LINE}),
    (
        "1b6bef8bb0ae32934a31bad5ac388c9f525205ff",
        "scripts/check_public_safety.py",
    ): frozenset({LEGACY_SCRIPT_URL_LINE}),
    (
        "4b7da9295ccfbe4cb27867601db0a70f9f3a405b",
        "README.md",
    ): frozenset({COMPANION_README_LINE}),
    (
        "2b096244fdaeb11875b0c2a88480ef9157ac4ec7",
        "README.md",
    ): frozenset({COMPANION_README_LINE}),
    (
        "2b096244fdaeb11875b0c2a88480ef9157ac4ec7",
        "scripts/check_public_safety.py",
    ): frozenset({LEGACY_SCRIPT_URL_LINE}),
}

SENSITIVE_JSON_KEYS = {
    "repository",
    "repository_full_name",
    "repo_full_name",
    "repository_url",
    "authorised_sha",
    "commit_sha",
    "owner",
    "username",
    "login",
    "email",
    "user_id",
    "owner_id",
    "workspace_uuid",
    "project_ref",
    "project_id",
    "application_uuid",
    "deployment_uuid",
    "client_id",
    "support_case",
    "support_case_id",
    "api_url",
    "database_url",
    "connection_string",
}

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("provider API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("email address", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
    ("Windows user path", re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\s]+")),
    ("POSIX user path", re.compile(r"(?i)(?:^|[\s\"'])(?:/home|/Users)/[^/\s\"']+")),
    ("GitHub repository URL", re.compile(r"(?i)https?://(?:www\.|api\.)?github\.com/(?:repos/)?[A-Z0-9_.-]+/[A-Z0-9_.-]+")),
    ("raw GitHub repository URL", re.compile(r"(?i)https?://raw\.githubusercontent\.com/[A-Z0-9_.-]+/[A-Z0-9_.-]+")),
    ("repository slug assignment", re.compile(r"""(?ix)
        ["']?(?:repository|repo_full_name|repository_full_name|repository_url)["']?
        \s*[:=]\s*
        ["'][A-Z0-9_.-]+/[A-Z0-9_.-]+["']
    """)),
    ("identity field assignment", re.compile(r"""(?ix)
        ["']?(?:owner|username|login|email|user_id|owner_id)["']?
        \s*[:=]\s*
        ["'][^"']+["']
    """)),
    ("provider identifier assignment", re.compile(r"""(?ix)
        ["']?(?:workspace_uuid|project_ref|project_id|application_uuid|deployment_uuid|client_id|support_case_id?)["']?
        \s*[:=]\s*
        ["'][^"']+["']
    """)),
    ("UUID", re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")),
    ("credential in URL", re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@")),
    ("sensitive query parameter", re.compile(r"(?i)[?&](?:token|api_key|apikey|secret|password|key)=[^&\s]+")),
    ("credential assignment", re.compile(r"""(?ix)
        \b(?:token|api[_-]?key|secret|password|passwd|connection[_-]?string)\b
        \s*[:=]\s*
        ["'](?!REDACTED|PLACEHOLDER|EXAMPLE|CHANGEME)[^"']{8,}["']
    """)),
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def decode_text(path: Path) -> str | None:
    data = path.read_bytes()
    if len(data) > MAX_TEXT_BYTES or b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def mask_exact_lines(text: str, allowed_lines: frozenset[str]) -> str:
    if not allowed_lines:
        return text

    masked: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        ending = raw_line[len(content):]
        if content in allowed_lines:
            content = content.replace(COMPANION_URL, URL_MASK)
        masked.append(content + ending)
    return "".join(masked)


def prepare_tracked_text(label: str, text: str) -> tuple[str, list[str]]:
    if label != "README.md":
        return text, []

    lines = text.splitlines()
    canonical_count = sum(line == COMPANION_README_LINE for line in lines)
    url_count = text.count(COMPANION_URL)
    failures: list[str] = []

    if canonical_count != 1:
        failures.append(
            f"{label}: expected exactly one canonical companion documentation line, "
            f"found {canonical_count}"
        )
    if url_count != 1:
        failures.append(
            f"{label}: expected exactly one companion documentation URL, found {url_count}"
        )

    if failures:
        return text, failures
    return mask_exact_lines(text, frozenset({COMPANION_README_LINE})), []


def prepare_historical_text(commit: str, label: str, text: str) -> str:
    allowed_lines = HISTORICAL_ALLOWED_LINES.get((commit, label), frozenset())
    return mask_exact_lines(text, allowed_lines)


def scan_text(label: str, text: str) -> list[str]:
    failures: list[str] = []
    for rule_name, pattern in RULES:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            failures.append(f"{label}:{line}: {rule_name}")
    return failures


def walk_json(value: object, label: str, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in SENSITIVE_JSON_KEYS:
                failures.append(f"{label}: forbidden JSON key at {path}.{key}")
            failures.extend(walk_json(item, label, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(walk_json(item, label, f"{path}[{index}]"))
    elif isinstance(value, str):
        failures.extend(scan_text(f"{label}:{path}", value))
    return failures


def scan_jsonl(path: Path) -> list[str]:
    failures: list[str] = []
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}:{number}: invalid JSON: {exc.msg}")
            continue
        failures.extend(walk_json(record, f"{path.relative_to(ROOT)}:{number}"))
    return failures


def changed_files_in_commit(commit: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            commit,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def added_lines_for_path(commit: str, label: str) -> str:
    patch = subprocess.run(
        [
            "git",
            "show",
            "--format=",
            "--unified=0",
            "--no-renames",
            commit,
            "--",
            label,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def added_lines_since_baseline() -> Iterable[tuple[str, str, str]]:
    if not BASELINE_FILE.exists():
        raise RuntimeError("missing .public-safety-baseline")
    baseline = BASELINE_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise RuntimeError("invalid .public-safety-baseline")
    result = subprocess.run(
        ["git", "rev-list", "--reverse", f"{baseline}..HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for commit in result.stdout.splitlines():
        for label in changed_files_in_commit(commit):
            additions = added_lines_for_path(commit, label)
            if additions:
                yield commit, label, additions


def main() -> int:
    failures: list[str] = []

    for path in tracked_files():
        text = decode_text(path)
        if text is None:
            continue
        label = str(path.relative_to(ROOT))
        prepared, policy_failures = prepare_tracked_text(label, text)
        failures.extend(policy_failures)
        failures.extend(scan_text(label, prepared))

    jsonl = ROOT / "evaluations.jsonl"
    if jsonl.exists():
        failures.extend(scan_jsonl(jsonl))

    try:
        for commit, label, additions in added_lines_since_baseline():
            prepared = prepare_historical_text(commit, label, additions)
            failures.extend(
                scan_text(f"commit:{commit[:12]}:{label}:added-lines", prepared)
            )
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        failures.append(f"history scan failed: {exc}")

    if failures:
        print("Public-safety scan failed.", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Public-safety scan passed: tracked tree, JSONL keys, and post-baseline added lines are clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
