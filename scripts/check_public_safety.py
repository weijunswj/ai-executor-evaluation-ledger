#!/usr/bin/env python3
"""Fail closed when public ledger content contains secrets or identifying metadata."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = ROOT / ".public-safety-baseline"
MAX_TEXT_BYTES = 2_000_000
GENERIC_HISTORY_BASELINE = "c644a6032dec6709ff08b10f8bfb4fe53de28b69"
UUID_HISTORY_ACTIVATION_HEAD = "d54fb99da162f49ccb616a8756725b9aea83ac1d"
PR_ACTIVATION_HEAD = "10f40ea2f820f4a6230355502639bd7a238b2c45"
CANONICAL_MAIN_BASE = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
PRE_ACTIVATION_OCCURRENCE_COUNT = 571
ACTIVATION_MANIFEST_RELATIVE_PATH = Path(
    "migrations/unicode-identity-history-activation.json"
)
ACTIVATION_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "pr_activation_head",
        "canonical_main_base",
        "generic_history_baseline",
        "pre_activation_occurrence_count",
        "pre_activation_inventory_sha256",
        "identity_rule_set_sha256",
    }
)

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

UUID_RULE = (
    "UUID",
    re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"),
)
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
    UUID_RULE,
    ("prohibited UUID assignment", re.compile(r"""(?ix)
        ["']?(?:workspace_uuid|project_ref|project_id|application_uuid|deployment_uuid|client_id|support_case_id?|owner|user_id|owner_id)["']?
        \s*[:=]\s*
        ["'][0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}["']
    """)),
    ("credential in URL", re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@")),
    ("sensitive query parameter", re.compile(r"(?i)[?&](?:token|api_key|apikey|secret|password|key)=[^&\s]+")),
    ("credential assignment", re.compile(r"""(?ix)
        \b(?:token|api[_-]?key|secret|password|passwd|connection[_-]?string)\b
        \s*[:=]\s*
        ["'](?!REDACTED|PLACEHOLDER|EXAMPLE|CHANGEME)[^"']{8,}["']
    """)),
)
# The UUID rule is prospective. Immutable history before DL-153-007 is still
# covered by every rule that was authoritative when that history was accepted.
HISTORICAL_RULES = tuple(rule for rule in RULES if rule != UUID_RULE)


INFERENCE_IDENTITY_WORD = "reason" + "ing"
COGNITIVE_SETTING_PARTS = ("think" + "ing", "setting")
NATIVE_CLASSIFICATION_WORDS = ("native", INFERENCE_IDENTITY_WORD, "classification")
GPT_MODEL_WORDS = ("GPT", "5", "6", "Sol")
CLAUDE_48_MODEL_WORDS = ("Claude", "Opus", "4", "8")
CLAUDE_5_MODEL_WORDS = ("Claude", "Opus", "5")
MEDIUM_SETTING_WORD = "Medium"
HIGH_SETTING_WORD = "High"
MAX_SETTING_WORD = "Max"
ULTRA_SETTING_WORD = "Ultra"
GPT_MODEL_NAME = "-".join(GPT_MODEL_WORDS[:2]) + "." + GPT_MODEL_WORDS[2] + " " + GPT_MODEL_WORDS[3]
CLAUDE_48_MODEL_NAME = " ".join(CLAUDE_48_MODEL_WORDS[:2]) + " " + ".".join(CLAUDE_48_MODEL_WORDS[2:])
CLAUDE_5_MODEL_NAME = " ".join(CLAUDE_5_MODEL_WORDS)

FORBIDDEN_LEDGER_IDENTITY_WORDS = (
    ("requested", INFERENCE_IDENTITY_WORD, "level"),
    ("observed", INFERENCE_IDENTITY_WORD, "mode"),
    COGNITIVE_SETTING_PARTS,
    NATIVE_CLASSIFICATION_WORDS,
    (INFERENCE_IDENTITY_WORD, "exposure", "status"),
    (INFERENCE_IDENTITY_WORD, "grouping"),
    (INFERENCE_IDENTITY_WORD, "level"),
    (INFERENCE_IDENTITY_WORD, "mode"),
    (*CLAUDE_48_MODEL_WORDS, HIGH_SETTING_WORD),
    (*CLAUDE_48_MODEL_WORDS, ULTRA_SETTING_WORD, HIGH_SETTING_WORD),
    (*CLAUDE_5_MODEL_WORDS, MAX_SETTING_WORD),
    (*GPT_MODEL_WORDS, MEDIUM_SETTING_WORD),
    (*GPT_MODEL_WORDS, HIGH_SETTING_WORD),
    (*GPT_MODEL_WORDS, MAX_SETTING_WORD),
)

FORBIDDEN_LEDGER_IDENTITY_TOKENS = frozenset(
    {
        "requested_" + INFERENCE_IDENTITY_WORD + "_level",
        "observed_" + INFERENCE_IDENTITY_WORD + "_mode",
        "_".join(COGNITIVE_SETTING_PARTS),
        "_".join(NATIVE_CLASSIFICATION_WORDS),
        INFERENCE_IDENTITY_WORD + "_exposure_status",
        INFERENCE_IDENTITY_WORD + "_grouping",
        INFERENCE_IDENTITY_WORD + "_level",
        INFERENCE_IDENTITY_WORD + "_mode",
        CLAUDE_48_MODEL_NAME + " " + HIGH_SETTING_WORD,
        CLAUDE_48_MODEL_NAME + " " + ULTRA_SETTING_WORD + " " + HIGH_SETTING_WORD,
        CLAUDE_5_MODEL_NAME + " " + MAX_SETTING_WORD,
        GPT_MODEL_NAME + " " + MEDIUM_SETTING_WORD,
        GPT_MODEL_NAME + " " + HIGH_SETTING_WORD,
        GPT_MODEL_NAME + " " + MAX_SETTING_WORD,
    }
)

LEGACY_IDENTITY_SEPARATOR = r"[\s_.:/\\-]*"


def _identity_pattern(*words: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z0-9])"
        + LEGACY_IDENTITY_SEPARATOR.join(re.escape(word) for word in words)
        + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


FORBIDDEN_LEDGER_IDENTITY_PATTERNS = tuple(
    _identity_pattern(*words) for words in FORBIDDEN_LEDGER_IDENTITY_WORDS
)

FORBIDDEN_LEDGER_IDENTITY_SEQUENCES = tuple(
    tuple(
        unicodedata.normalize("NFKC", word).casefold()
        for word in words
    )
    for words in FORBIDDEN_LEDGER_IDENTITY_WORDS
)
FORBIDDEN_LEDGER_IDENTITY_RULES = tuple(
    (f"unicode_identity_{index:03d}", sequence)
    for index, sequence in enumerate(
        FORBIDDEN_LEDGER_IDENTITY_SEQUENCES,
        start=1,
    )
)
FORBIDDEN_SEQUENCES_BY_FIRST_TOKEN = {
    first: tuple(
        (rule_id, sequence)
        for rule_id, sequence in FORBIDDEN_LEDGER_IDENTITY_RULES
        if sequence[0] == first
    )
    for first in {
        sequence[0]
        for sequence in FORBIDDEN_LEDGER_IDENTITY_SEQUENCES
    }
}


@dataclass(frozen=True)
class IdentityMatch:
    rule_id: str
    offset: int
    line_number: int


@dataclass(frozen=True)
class AddedLineRecord:
    line_number: int
    added_line_ordinal: int
    line_bytes: bytes
    text: str


def _unicode_alphanumeric_runs(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Return NFKC/case-folded Unicode alphanumeric runs and their offsets."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    runs: list[tuple[str, int]] = []
    start: int | None = None
    for index, character in enumerate(normalized):
        if character.isalnum():
            if start is None:
                start = index
            continue
        if start is not None:
            runs.append((normalized[start:index], start))
            start = None
    if start is not None:
        runs.append((normalized[start:], start))
    return normalized, runs


def tracked_files(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def decode_text(path: Path) -> str | None:
    if not path.exists():
        return None
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


def scan_text(
    label: str,
    text: str,
    rules: Iterable[tuple[str, re.Pattern[str]]] = RULES,
) -> list[str]:
    failures: list[str] = []
    for rule_name, pattern in rules:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            failures.append(f"{label}:{line}: {rule_name}")
    return failures


def identity_rule_set_sha256() -> str:
    """Hash stable rule structure without serialising prohibited sequences."""

    structures = []
    for rule_id, sequence in FORBIDDEN_LEDGER_IDENTITY_RULES:
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


def iter_ledger_identity_matches(text: str) -> list[IdentityMatch]:
    """Return privacy-safe match metadata for the normalized identity rules."""

    normalized, runs = _unicode_alphanumeric_runs(text)
    run_values = tuple(value for value, _offset in runs)
    matches: list[IdentityMatch] = []
    for index, (first, offset) in enumerate(runs):
        for rule_id, sequence in FORBIDDEN_SEQUENCES_BY_FIRST_TOKEN.get(
            first,
            (),
        ):
            width = len(sequence)
            if run_values[index : index + width] == sequence:
                matches.append(
                    IdentityMatch(
                        rule_id=rule_id,
                        offset=offset,
                        line_number=normalized.count("\n", 0, offset) + 1,
                    )
                )
    return matches


def scan_ledger_identity(label: str, text: str) -> list[str]:
    """Reject normalized model-setting identities in every tracked directory."""

    return [
        f"{label}:{match.line_number}: forbidden ledger identity token "
        f"[{match.rule_id}]"
        for match in iter_ledger_identity_matches(text)
    ]


def scan_public_text(
    label: str,
    text: str,
    *,
    generic_text: str | None = None,
    policy_failures: Iterable[str] = (),
    generic_rules: Iterable[tuple[str, re.Pattern[str]]] = RULES,
) -> list[str]:
    """Apply the one generic and normalized-identity scanning pipeline."""

    failures = list(policy_failures)
    failures.extend(
        scan_text(
            label,
            text if generic_text is None else generic_text,
            generic_rules,
        )
    )
    failures.extend(scan_ledger_identity(label, text))
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


def scan_jsonl(path: Path, *, root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(root)}:{number}: invalid JSON: {exc.msg}")
            continue
        failures.extend(walk_json(record, f"{path.relative_to(root)}:{number}"))
    return failures


def changed_files_in_commit(commit: str, *, root: Path = ROOT) -> list[str]:
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
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def added_line_byte_records_for_path(
    commit: str,
    label: str,
    *,
    root: Path = ROOT,
) -> list[AddedLineRecord]:
    patch = subprocess.run(
        [
            "git",
            "show",
            "--format=",
            "--unified=0",
            "--no-renames",
            commit,
            "--",
            ":(literal)" + label,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    ).stdout
    records: list[AddedLineRecord] = []
    new_line: int | None = None
    added_line_ordinal = 0
    for raw_line in patch.splitlines():
        try:
            line = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise RuntimeError("history patch is not strict UTF-8") from error
        if line.startswith("@@ "):
            match = re.match(
                r"^@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,[0-9]+)? @@",
                line,
            )
            if match is None:
                raise RuntimeError("history patch hunk is malformed")
            new_line = int(match.group(1))
            continue
        if new_line is None or line.startswith(
            ("diff ", "index ", "---", "+++")
        ):
            continue
        if line.startswith("+"):
            added_line_ordinal += 1
            records.append(
                AddedLineRecord(
                    line_number=new_line,
                    added_line_ordinal=added_line_ordinal,
                    line_bytes=raw_line[1:],
                    text=line[1:],
                )
            )
            new_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" "):
            new_line += 1
    return records


def added_line_records_for_path(
    commit: str,
    label: str,
    *,
    root: Path = ROOT,
) -> list[tuple[int, str]]:
    return [
        (record.line_number, record.text)
        for record in added_line_byte_records_for_path(
            commit,
            label,
            root=root,
        )
    ]


def added_lines_for_path(
    commit: str,
    label: str,
    *,
    root: Path = ROOT,
) -> str:
    return "\n".join(
        text
        for _line_number, text in added_line_records_for_path(
            commit,
            label,
            root=root,
        )
    )


def added_lines_since_baseline(
    root: Path = ROOT,
) -> Iterable[tuple[str, str, int, str]]:
    baseline_file = root / ".public-safety-baseline"
    if not baseline_file.exists():
        raise RuntimeError("missing .public-safety-baseline")
    baseline = baseline_file.read_text(encoding="utf-8").strip()
    if baseline != GENERIC_HISTORY_BASELINE:
        raise RuntimeError("invalid .public-safety-baseline")
    yield from added_lines_in_range(baseline, root=root)


def _git_commit_exists(root: Path, revision: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("history ancestry is unavailable")
    return result.returncode == 0


def _require_complete_history(root: Path) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.strip() != "false":
        raise RuntimeError("git history is incomplete")


def added_lines_in_range(
    start: str,
    *,
    end: str = "HEAD",
    root: Path = ROOT,
) -> Iterable[tuple[str, str, int, str]]:
    _require_complete_history(root)
    if not _git_commit_exists(root, start) or not _git_commit_exists(root, end):
        raise RuntimeError("history range authority is unavailable")
    if not _is_ancestor(root, start, end):
        raise RuntimeError("history range authority is not an ancestor")
    result = subprocess.run(
        ["git", "rev-list", "--reverse", f"{start}..{end}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    for commit in result.stdout.splitlines():
        for label in changed_files_in_commit(commit, root=root):
            for line_number, addition in added_line_records_for_path(
                commit,
                label,
                root=root,
            ):
                yield commit, label, line_number, addition


def _git_blob(root: Path, revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("history authority blob is unavailable")
    return result.stdout


def _baseline_blob_is_unchanged(root: Path) -> None:
    expected = (GENERIC_HISTORY_BASELINE + "\n").encode("ascii")
    head_blob = _git_blob(root, "HEAD", ".public-safety-baseline")
    if head_blob != expected:
        raise RuntimeError("generic history baseline changed")
    if _git_commit_exists(root, PR_ACTIVATION_HEAD):
        activation_blob = _git_blob(
            root,
            PR_ACTIVATION_HEAD,
            ".public-safety-baseline",
        )
        if activation_blob != head_blob:
            raise RuntimeError("generic history baseline changed")


def canonical_inventory_bytes(
    descriptors: Iterable[Mapping[str, Any]],
) -> bytes:
    required = {
        "commit_sha",
        "path",
        "added_line_ordinal",
        "match_ordinal",
        "rule_id",
        "added_line_sha256",
    }
    canonical_items: list[dict[str, Any]] = []
    fingerprints: set[bytes] = set()
    for descriptor in descriptors:
        if set(descriptor) != required:
            raise RuntimeError("pre-activation descriptor is malformed")
        item = dict(descriptor)
        if (
            not isinstance(item["commit_sha"], str)
            or re.fullmatch(r"[0-9a-f]{40}", item["commit_sha"]) is None
            or not isinstance(item["path"], str)
            or not item["path"]
            or Path(item["path"]).is_absolute()
            or ".." in Path(item["path"]).parts
            or not isinstance(item["added_line_ordinal"], int)
            or isinstance(item["added_line_ordinal"], bool)
            or item["added_line_ordinal"] < 1
            or not isinstance(item["match_ordinal"], int)
            or isinstance(item["match_ordinal"], bool)
            or item["match_ordinal"] < 1
            or not isinstance(item["rule_id"], str)
            or re.fullmatch(r"unicode_identity_[0-9]{3}", item["rule_id"])
            is None
            or not isinstance(item["added_line_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["added_line_sha256"])
            is None
        ):
            raise RuntimeError("pre-activation descriptor is malformed")
        fingerprint = json.dumps(
            item,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if fingerprint in fingerprints:
            raise RuntimeError("duplicate pre-activation descriptor")
        fingerprints.add(fingerprint)
        canonical_items.append(item)
    canonical_items.sort(
        key=lambda item: (
            item["commit_sha"],
            item["path"],
            item["added_line_ordinal"],
            item["match_ordinal"],
            item["rule_id"],
            item["added_line_sha256"],
        )
    )
    return (
        json.dumps(
            canonical_items,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


@lru_cache(maxsize=32)
def _pre_activation_inventory_cached(
    root_text: str,
    generic_baseline: str,
    activation_head: str,
    _rule_set_sha256: str,
) -> tuple[int, str]:
    root = Path(root_text)
    descriptors: list[dict[str, Any]] = []
    _require_complete_history(root)
    if not _git_commit_exists(root, generic_baseline):
        raise RuntimeError("generic history baseline is unavailable")
    if not _git_commit_exists(root, activation_head):
        raise RuntimeError("PR activation head is unavailable")
    if not _is_ancestor(root, generic_baseline, activation_head):
        raise RuntimeError("pre-activation range is invalid")
    commits = subprocess.run(
        [
            "git",
            "rev-list",
            "--reverse",
            f"{generic_baseline}..{activation_head}",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for commit in commits:
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise RuntimeError("pre-activation commit identity is malformed")
        for label in changed_files_in_commit(commit, root=root):
            records = added_line_byte_records_for_path(
                commit,
                label,
                root=root,
            )
            for record in records:
                matches = iter_ledger_identity_matches(record.text)
                line_hash = hashlib.sha256(record.line_bytes).hexdigest()
                for match_ordinal, match in enumerate(matches, start=1):
                    descriptors.append(
                        {
                            "commit_sha": commit,
                            "path": label,
                            "added_line_ordinal": record.added_line_ordinal,
                            "match_ordinal": match_ordinal,
                            "rule_id": match.rule_id,
                            "added_line_sha256": line_hash,
                        }
                    )
    canonical = canonical_inventory_bytes(descriptors)
    return len(descriptors), hashlib.sha256(canonical).hexdigest()


def pre_activation_inventory(root: Path = ROOT) -> tuple[int, str]:
    """Recompute privacy-safe descriptors once per immutable process authority."""

    return _pre_activation_inventory_cached(
        str(root.resolve()),
        GENERIC_HISTORY_BASELINE,
        PR_ACTIVATION_HEAD,
        identity_rule_set_sha256(),
    )


def expected_activation_manifest(root: Path = ROOT) -> dict[str, Any]:
    count, inventory_hash = pre_activation_inventory(root)
    if count != PRE_ACTIVATION_OCCURRENCE_COUNT:
        raise RuntimeError("pre-activation inventory count mismatch")
    return {
        "schema_version": 1,
        "manifest_type": "unicode_identity_history_activation",
        "pr_activation_head": PR_ACTIVATION_HEAD,
        "canonical_main_base": CANONICAL_MAIN_BASE,
        "generic_history_baseline": GENERIC_HISTORY_BASELINE,
        "pre_activation_occurrence_count": count,
        "pre_activation_inventory_sha256": inventory_hash,
        "identity_rule_set_sha256": identity_rule_set_sha256(),
    }


def _closed_json_object(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError("activation manifest has duplicate fields")
            value[key] = item
        return value

    try:
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(decoded, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimeError("activation manifest is malformed") from error
    if not isinstance(value, dict):
        raise RuntimeError("activation manifest is malformed")
    return value


def validate_activation_manifest(root: Path = ROOT) -> dict[str, Any]:
    path = root / ACTIVATION_MANIFEST_RELATIVE_PATH
    try:
        value = _closed_json_object(path.read_bytes())
    except OSError as error:
        raise RuntimeError("activation manifest is unavailable") from error
    if set(value) != ACTIVATION_MANIFEST_FIELDS:
        raise RuntimeError("activation manifest fields are not closed")
    expected = expected_activation_manifest(root)
    if value != expected:
        raise RuntimeError("activation manifest authority mismatch")
    _baseline_blob_is_unchanged(root)
    return value


def unicode_history_start(root: Path, manifest: Mapping[str, Any]) -> tuple[str, str]:
    _require_complete_history(root)
    activation = str(manifest["pr_activation_head"])
    canonical = str(manifest["canonical_main_base"])
    if _git_commit_exists(root, activation) and _is_ancestor(
        root,
        activation,
    ):
        return activation, "pr-descendant"
    if not _git_commit_exists(root, canonical):
        raise RuntimeError("canonical history authority is unavailable")
    if not _is_ancestor(root, canonical):
        raise RuntimeError("no authorised Unicode history ancestry")
    return canonical, "canonical-main-squash"


def uuid_history_start(root: Path) -> tuple[str, str]:
    """Select the prospective UUID-rule history without rewriting legacy history."""

    _require_complete_history(root)
    if _git_commit_exists(root, UUID_HISTORY_ACTIVATION_HEAD) and _is_ancestor(
        root,
        UUID_HISTORY_ACTIVATION_HEAD,
    ):
        return UUID_HISTORY_ACTIVATION_HEAD, "pr-descendant"
    if not _git_commit_exists(root, CANONICAL_MAIN_BASE):
        raise RuntimeError("canonical history authority is unavailable")
    if not _is_ancestor(root, CANONICAL_MAIN_BASE):
        raise RuntimeError("no authorised UUID history ancestry")
    return CANONICAL_MAIN_BASE, "canonical-main-squash"


def tree_failures(root: Path) -> list[str]:
    """Return privacy-safe failures for a complete isolated candidate tree."""
    failures: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        text = decode_text(path)
        if text is None:
            continue
        label = path.relative_to(root).as_posix()
        prepared, policy_failures = prepare_tracked_text(label, text)
        failures.extend(
            scan_public_text(
                label,
                text,
                generic_text=prepared,
                policy_failures=policy_failures,
            )
        )

    jsonl = root / "evaluations.jsonl"
    if jsonl.exists():
        failures.extend(scan_jsonl(jsonl, root=root))

    return failures


def history_failures(root: Path = ROOT) -> list[str]:
    """Run the exact historical path used by hosted Public Safety."""

    failures: list[str] = []
    manifest = validate_activation_manifest(root)

    # The original generic rules retain their original baseline and exact line
    # exceptions. New prospective rules receive no authority over that range.
    for commit, label, line_number, addition in added_lines_since_baseline(root):
        prepared = prepare_historical_text(commit, label, addition)
        failures.extend(
            scan_text(
                f"commit:{commit[:12]}:{label}:added-line-{line_number}",
                prepared,
                HISTORICAL_RULES,
            )
        )

    unicode_start, _mode = unicode_history_start(root, manifest)
    for commit, label, line_number, addition in added_lines_in_range(
        unicode_start,
        root=root,
    ):
        prepared = prepare_historical_text(commit, label, addition)
        failures.extend(
            scan_public_text(
                f"commit:{commit[:12]}:{label}:added-line-{line_number}",
                addition,
                generic_text=prepared,
                generic_rules=HISTORICAL_RULES,
            )
        )

    uuid_start, _mode = uuid_history_start(root)
    for commit, label, line_number, addition in added_lines_in_range(
        uuid_start,
        root=root,
    ):
        prepared = prepare_historical_text(commit, label, addition)
        failures.extend(
            scan_text(
                f"commit:{commit[:12]}:{label}:added-line-{line_number}",
                prepared,
                (UUID_RULE,),
            )
        )

    return sorted(set(failures))


def audit_tree(root: Path) -> int:
    """Scan an isolated candidate tree without consulting the live checkout."""

    return 1 if tree_failures(root) else 0


def main() -> int:
    failures = tree_failures(ROOT)

    try:
        failures.extend(history_failures(ROOT))
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        failures.append(f"history scan failed: {exc}")

    if failures:
        print("Public-safety scan failed.", file=sys.stderr)
        for failure in sorted(set(failures)):
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        "Public-safety scan passed: tracked and candidate text, generic history, "
        "and activated Unicode identity history are clean."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
