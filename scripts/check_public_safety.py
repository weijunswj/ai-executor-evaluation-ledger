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

ALLOWED_PUBLIC_GITHUB_URLS = frozenset(
    {
        "https://github.com/weijunswj/Custom-Instruction-Framework-For-Web-based-LLMs/blob/main/CUSTOM_INSTRUCTIONS.md",
    }
)
URL_TERMINATORS = frozenset(" \t\r\n)>]\"'")

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


def is_allowed_public_github_url(text: str, start: int) -> bool:
    for url in ALLOWED_PUBLIC_GITHUB_URLS:
        if not text.startswith(url, start):
            continue
        end = start + len(url)
        return end == len(text) or text[end] in URL_TERMINATORS
    return False


def scan_text(label: str, text: str) -> list[str]:
    failures: list[str] = []
    for rule_name, pattern in RULES:
        for match in pattern.finditer(text):
            if rule_name == "GitHub repository URL" and is_allowed_public_github_url(text, match.start()):
                continue
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


def added_lines_since_baseline() -> Iterable[tuple[str, str]]:
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
        patch = subprocess.run(
            ["git", "show", "--format=", "--unified=0", "--no-renames", commit],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        ).stdout
        additions = "\n".join(
            line[1:]
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        yield commit[:12], additions


def main() -> int:
    failures: list[str] = []

    for path in tracked_files():
        text = decode_text(path)
        if text is None:
            continue
        failures.extend(scan_text(str(path.relative_to(ROOT)), text))

    jsonl = ROOT / "evaluations.jsonl"
    if jsonl.exists():
        failures.extend(scan_jsonl(jsonl))

    try:
        for commit, additions in added_lines_since_baseline():
            failures.extend(scan_text(f"commit:{commit}:added-lines", additions))
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
