#!/usr/bin/env python3
"""Fail closed when public ledger content contains secrets or identifying metadata."""

from __future__ import annotations

import json
import hashlib
import io
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
LUNA_HISTORY_BASE = "da55c6ce1e3426b9b5eadfcb29fe41d8ce71e898"
LUNA_RED_PROOF_COMMIT = "d3624f0782329b2bd46ce56daf784e6a3c0d6fbb"
LUNA_TDD_HISTORY_ALLOWED_MATCHES = frozenset(
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
)
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
LUNA_MODEL_WORDS = ("GPT", "5", "6", "Luna")
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


LUNA_EXECUTION_SETTING_WORDS = (
    (*LUNA_MODEL_WORDS, MEDIUM_SETTING_WORD),
    (*LUNA_MODEL_WORDS, HIGH_SETTING_WORD),
    (*LUNA_MODEL_WORDS, MAX_SETTING_WORD),
)
LUNA_EXECUTION_SETTING_SEQUENCES = tuple(
    tuple(unicodedata.normalize("NFKC", word).casefold() for word in words)
    for words in LUNA_EXECUTION_SETTING_WORDS
)
LUNA_EXECUTION_SETTING_RULES = tuple(
    (f"luna_execution_setting_{index:03d}", sequence)
    for index, sequence in enumerate(LUNA_EXECUTION_SETTING_SEQUENCES, start=1)
)
LUNA_SEQUENCES_BY_FIRST_TOKEN = {
    first: tuple(
        (rule_id, sequence)
        for rule_id, sequence in LUNA_EXECUTION_SETTING_RULES
        if sequence[0] == first
    )
    for first in {sequence[0] for sequence in LUNA_EXECUTION_SETTING_SEQUENCES}
}

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

NORMALIZED_IDENTITY_RULE_MAPS = (
    FORBIDDEN_SEQUENCES_BY_FIRST_TOKEN,
    LUNA_SEQUENCES_BY_FIRST_TOKEN,
)
MAX_NORMALIZED_IDENTITY_SEQUENCE_LENGTH = max(
    len(sequence)
    for rules_by_first_token in NORMALIZED_IDENTITY_RULE_MAPS
    for rules in rules_by_first_token.values()
    for _rule_id, sequence in rules
)
NORMALIZED_IDENTITY_CARRY_LENGTH = MAX_NORMALIZED_IDENTITY_SEQUENCE_LENGTH - 1


@dataclass(frozen=True)
class IdentityMatch:
    rule_id: str
    offset: int
    line_number: int


@dataclass(frozen=True)
class NormalizedIdentityContextToken:
    value: str
    line_number: int
    is_key: bool


@dataclass(frozen=True)
class CrossRecordIdentityMatch:
    rule_id: str
    start_line: int
    end_line: int
    uses_key: bool


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


def _normalized_context_tokens(
    parts: Iterable[tuple[str, bool]],
    line_number: int,
) -> tuple[NormalizedIdentityContextToken, ...]:
    tokens: list[NormalizedIdentityContextToken] = []
    for text, is_key in parts:
        _normalized, runs = _unicode_alphanumeric_runs(text)
        tokens.extend(
            NormalizedIdentityContextToken(
                value=value,
                line_number=line_number,
                is_key=is_key,
            )
            for value, _offset in runs
        )
    return tuple(tokens)


def _bounded_normalized_context(
    tokens: tuple[NormalizedIdentityContextToken, ...],
) -> tuple[NormalizedIdentityContextToken, ...]:
    if NORMALIZED_IDENTITY_CARRY_LENGTH <= 0:
        return ()
    return tokens[-NORMALIZED_IDENTITY_CARRY_LENGTH:]


def _json_record_normalized_contexts(
    value_context: str,
    record_strings: list[tuple[str, bool]],
    line_number: int,
) -> tuple[
    tuple[NormalizedIdentityContextToken, ...],
    tuple[NormalizedIdentityContextToken, ...],
]:
    return (
        _normalized_context_tokens(((value_context, False),), line_number),
        _normalized_context_tokens(record_strings, line_number),
    )


def _cross_record_normalized_identity_matches(
    previous_contexts: Iterable[tuple[NormalizedIdentityContextToken, ...]],
    current_contexts: Iterable[tuple[NormalizedIdentityContextToken, ...]],
    rules_by_first_token: Mapping[
        str,
        tuple[tuple[str, tuple[str, ...]], ...],
    ],
) -> list[CrossRecordIdentityMatch]:
    aggregated: dict[tuple[str, int, int], bool] = {}
    for previous in previous_contexts:
        if not previous:
            continue
        for current in current_contexts:
            if not current:
                continue
            combined = previous + current
            boundary = len(previous)
            token_values = tuple(token.value for token in combined)
            for index, first in enumerate(token_values):
                for rule_id, sequence in rules_by_first_token.get(first, ()):
                    width = len(sequence)
                    end_index = index + width
                    if (
                        index >= boundary
                        or end_index <= boundary
                        or end_index > len(combined)
                        or token_values[index:end_index] != sequence
                    ):
                        continue
                    key = (
                        rule_id,
                        combined[index].line_number,
                        combined[end_index - 1].line_number,
                    )
                    uses_key = any(
                        token.is_key for token in combined[index:end_index]
                    )
                    aggregated[key] = aggregated.get(key, False) or uses_key
    return [
        CrossRecordIdentityMatch(
            rule_id=rule_id,
            start_line=start_line,
            end_line=end_line,
            uses_key=uses_key,
        )
        for (rule_id, start_line, end_line), uses_key in aggregated.items()
    ]


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


def _iter_normalized_identity_matches(
    text: str,
    rules_by_first_token: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]],
) -> list[IdentityMatch]:
    normalized, runs = _unicode_alphanumeric_runs(text)
    run_values = tuple(value for value, _offset in runs)
    matches: list[IdentityMatch] = []
    for index, (first, offset) in enumerate(runs):
        for rule_id, sequence in rules_by_first_token.get(first, ()):
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


def _iter_normalized_identity_run_spans(
    text: str,
    rules_by_first_token: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]],
) -> list[tuple[str, int, int, int, int]]:
    normalized, runs = _unicode_alphanumeric_runs(text)
    run_values = tuple(value for value, _offset in runs)
    matches: list[tuple[str, int, int, int, int]] = []
    for index, (first, offset) in enumerate(runs):
        for rule_id, sequence in rules_by_first_token.get(first, ()):
            width = len(sequence)
            if run_values[index : index + width] != sequence:
                continue
            last_value, last_offset = runs[index + width - 1]
            end_offset = last_offset + len(last_value)
            matches.append(
                (rule_id, index, index + width - 1, offset, end_offset)
            )
    return matches


def _iter_normalized_identity_line_spans(
    text: str,
    rules_by_first_token: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]],
) -> list[tuple[str, int, int]]:
    """Return privacy-safe normalized rule IDs with inclusive line spans."""

    normalized, runs = _unicode_alphanumeric_runs(text)
    run_values = tuple(value for value, _offset in runs)
    spans: list[tuple[str, int, int]] = []
    for index, (first, offset) in enumerate(runs):
        for rule_id, sequence in rules_by_first_token.get(first, ()):
            width = len(sequence)
            if run_values[index : index + width] != sequence:
                continue
            last_value, last_offset = runs[index + width - 1]
            end_offset = last_offset + len(last_value)
            spans.append(
                (
                    rule_id,
                    normalized.count("\n", 0, offset) + 1,
                    normalized.count("\n", 0, end_offset) + 1,
                )
            )
    return spans


def iter_ledger_identity_matches(text: str) -> list[IdentityMatch]:
    """Return privacy-safe match metadata for the normalized identity rules."""

    return _iter_normalized_identity_matches(text, FORBIDDEN_SEQUENCES_BY_FIRST_TOKEN)


def scan_ledger_identity(label: str, text: str) -> list[str]:
    """Reject normalized model-setting identities in every tracked directory."""

    return [
        f"{label}:{match.line_number}: forbidden ledger identity token "
        f"[{match.rule_id}]"
        for match in iter_ledger_identity_matches(text)
    ]


def scan_luna_execution_settings(label: str, text: str) -> list[str]:
    return [
        f"{label}:{match.line_number}: forbidden ledger identity token "
        f"[{match.rule_id}]"
        for match in _iter_normalized_identity_matches(
            text,
            LUNA_SEQUENCES_BY_FIRST_TOKEN,
        )
    ]


def scan_public_text(
    label: str,
    text: str,
    *,
    generic_text: str | None = None,
    policy_failures: Iterable[str] = (),
    generic_rules: Iterable[tuple[str, re.Pattern[str]]] = RULES,
    include_luna_execution_settings: bool = True,
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
    if include_luna_execution_settings:
        failures.extend(scan_luna_execution_settings(label, text))
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
        failures.extend(scan_public_text(f"{label}:{path}", value))
    return failures


def _collect_json_record_strings(
    value: object,
    label: str,
    path: str = "$",
) -> tuple[list[str], list[str], list[tuple[str, bool]]]:
    """Validate JSON keys while retaining value and key-aware contexts."""

    failures: list[str] = []
    string_values: list[str] = []
    record_strings: list[tuple[str, bool]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in SENSITIVE_JSON_KEYS:
                failures.append(f"{label}: forbidden JSON key at {path}.{key}")
            record_strings.append((key, True))
            child_failures, child_strings, child_record_strings = _collect_json_record_strings(
                item,
                label,
                f"{path}.{key}",
            )
            failures.extend(child_failures)
            string_values.extend(child_strings)
            record_strings.extend(child_record_strings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_failures, child_strings, child_record_strings = _collect_json_record_strings(
                item,
                label,
                f"{path}[{index}]",
            )
            failures.extend(child_failures)
            string_values.extend(child_strings)
            record_strings.extend(child_record_strings)
    elif isinstance(value, str):
        string_values.append(value)
        record_strings.append((value, False))
    return failures, string_values, record_strings


def _scan_json_record(
    value: object,
    label: str,
) -> tuple[list[str], tuple[str, list[tuple[str, bool]]]]:
    """Scan one record in value-only and key-aware deterministic contexts."""

    failures, string_values, record_strings = _collect_json_record_strings(value, label)
    value_context = " ".join(string_values)
    record_context = " ".join(text for text, _is_key in record_strings)
    if value_context:
        failures.extend(scan_public_text(label, value_context))
    seen_failures = set(failures)
    if record_context:
        for failure in scan_public_text(label, record_context):
            if failure not in seen_failures:
                failures.append(failure)
                seen_failures.add(failure)
    return failures, (value_context, record_strings)


def _luna_json_record_occurrences(
    value_context: str,
    record_strings: list[tuple[str, bool]],
) -> dict[str, list[tuple[int, int]]]:
    occurrences = _luna_match_occurrence_spans_by_rule(value_context)
    record_context = " ".join(text for text, _is_key in record_strings)
    if not record_context:
        return occurrences

    normalized, runs = _unicode_alphanumeric_runs(record_context)
    part_ranges: list[tuple[int, int, bool]] = []
    part_offset = 0
    for text, is_key in record_strings:
        normalized_part = unicodedata.normalize("NFKC", text).casefold()
        part_ranges.append(
            (part_offset, part_offset + len(normalized_part), is_key)
        )
        part_offset += len(normalized_part) + 1

    for (
        rule_id,
        start_index,
        end_index,
        start_offset,
        end_offset,
    ) in _iter_normalized_identity_run_spans(
        record_context,
        LUNA_SEQUENCES_BY_FIRST_TOKEN,
    ):
        uses_key = any(
            is_key
            for _run_value, run_offset in runs[start_index : end_index + 1]
            for part_start, part_end, is_key in part_ranges
            if part_start <= run_offset < part_end
        )
        if not uses_key:
            continue
        occurrences.setdefault(rule_id, []).append(
            (
                normalized.count("\n", 0, start_offset) + 1,
                normalized.count("\n", 0, end_offset) + 1,
            )
        )
    return occurrences


def _parse_jsonl_record(raw_line: bytes) -> object:
    if b"\0" in raw_line:
        raise ValueError("JSONL record contains a NUL byte")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        record: dict[str, object] = {}
        for key, value in pairs:
            if key in record:
                raise ValueError("JSONL record contains duplicate object keys")
            record[key] = value
        return record

    return json.loads(
        raw_line.decode("utf-8", errors="strict"),
        object_pairs_hook=reject_duplicates,
    )


def _iter_jsonl_blob_records(raw: bytes) -> Iterable[tuple[int, object]]:
    """Yield strict, parsed JSONL records without decoding the whole blob."""

    for number, raw_line in enumerate(io.BytesIO(raw), start=1):
        if not raw_line.strip():
            continue
        try:
            record = _parse_jsonl_record(raw_line)
        except UnicodeDecodeError as error:
            raise RuntimeError(
                "Luna history JSONL is not strict UTF-8"
            ) from error
        except json.JSONDecodeError as error:
            raise RuntimeError("Luna history JSONL contains invalid JSON") from error
        except ValueError as error:
            raise RuntimeError("Luna history JSONL contains invalid text") from error
        yield number, record


def scan_jsonl(path: Path, *, root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    label = path.relative_to(root).as_posix()
    previous_value_context: tuple[NormalizedIdentityContextToken, ...] = ()
    previous_record_context: tuple[NormalizedIdentityContextToken, ...] = ()
    with path.open("rb") as handle:
        for number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = _parse_jsonl_record(raw_line)
            except UnicodeDecodeError:
                failures.append(f"{label}:{number}: invalid UTF-8")
                previous_value_context = ()
                previous_record_context = ()
                continue
            except json.JSONDecodeError as exc:
                failures.append(f"{label}:{number}: invalid JSON: {exc.msg}")
                previous_value_context = ()
                previous_record_context = ()
                continue
            except ValueError as exc:
                failures.append(f"{label}:{number}: invalid text: {exc}")
                previous_value_context = ()
                previous_record_context = ()
                continue
            record_failures, (value_context, record_strings) = _scan_json_record(
                record,
                f"{label}:{number}",
            )
            failures.extend(record_failures)
            value_tokens, record_tokens = _json_record_normalized_contexts(
                value_context,
                record_strings,
                number,
            )
            for rules_by_first_token in NORMALIZED_IDENTITY_RULE_MAPS:
                for match in _cross_record_normalized_identity_matches(
                    (previous_value_context, previous_record_context),
                    (value_tokens, record_tokens),
                    rules_by_first_token,
                ):
                    failure = (
                        f"{label}:{match.end_line}: forbidden ledger identity token "
                        f"[{match.rule_id}]"
                    )
                    if failure not in failures:
                        failures.append(failure)
            previous_value_context = _bounded_normalized_context(value_tokens)
            previous_record_context = _bounded_normalized_context(record_tokens)
    return failures


def _commit_parents(root: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", commit],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("history parent authority is unavailable")
    fields = result.stdout.split()
    if not fields or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None:
        raise RuntimeError("history parent authority is malformed")
    parents = fields[1:]
    if any(re.fullmatch(r"[0-9a-f]{40}", parent) is None for parent in parents):
        raise RuntimeError("history parent authority is malformed")
    return parents


def changed_files_in_commit(commit: str, *, root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-m",
            "-z",
            commit,
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted(
        {
            item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        }
    )


def _jsonl_finding_signature(failure: str) -> str:
    return failure.rsplit(": ", 1)[-1]


def _jsonl_finding_surplus(
    after: Iterable[str],
    parents: Iterable[Iterable[str]],
) -> list[str]:
    available: dict[str, int] = {}
    for parent_findings in parents:
        for failure in parent_findings:
            signature = _jsonl_finding_signature(failure)
            available[signature] = available.get(signature, 0) + 1

    surplus: list[str] = []
    for failure in after:
        signature = _jsonl_finding_signature(failure)
        remaining = available.get(signature, 0)
        if remaining:
            available[signature] = remaining - 1
        else:
            surplus.append(failure)
    return surplus


def _luna_history_blob_scan(
    raw: bytes,
    label: str,
    *,
    root: Path,
    revision: str | None,
) -> tuple[dict[str, list[tuple[int, int]]], list[str]]:
    if not label.casefold().endswith(".jsonl"):
        if raw and _git_revision_blob_is_binary(root, revision, label):
            return {}, []
        return _luna_match_occurrence_spans_by_rule(_decode_luna_history_blob(raw)), []

    matches: dict[str, list[tuple[int, int]]] = {}
    non_luna_failures: list[str] = []
    previous_value_context: tuple[NormalizedIdentityContextToken, ...] = ()
    previous_record_context: tuple[NormalizedIdentityContextToken, ...] = ()
    for number, record in _iter_jsonl_blob_records(raw):
        record_failures, (value_context, record_strings) = _scan_json_record(
            record,
            f"{label}:{number}",
        )
        non_luna_failures.extend(
            failure
            for failure in record_failures
            if "luna_execution_setting_" not in failure
        )
        for rule_id, spans in _luna_json_record_occurrences(
            value_context,
            record_strings,
        ).items():
            matches.setdefault(rule_id, []).extend(
                (number, number) for _start_line, _end_line in spans
            )
        value_tokens, record_tokens = _json_record_normalized_contexts(
            value_context,
            record_strings,
            number,
        )
        for rules_by_first_token in NORMALIZED_IDENTITY_RULE_MAPS:
            cross_matches = _cross_record_normalized_identity_matches(
                (previous_value_context, previous_record_context),
                (value_tokens, record_tokens),
                rules_by_first_token,
            )
            if rules_by_first_token is LUNA_SEQUENCES_BY_FIRST_TOKEN:
                for match in cross_matches:
                    matches.setdefault(match.rule_id, []).append(
                        (match.start_line, match.end_line)
                    )
            else:
                non_luna_failures.extend(
                    f"{label}:{match.end_line}: forbidden ledger identity token "
                    f"[{match.rule_id}]"
                    for match in cross_matches
                )
        previous_value_context = _bounded_normalized_context(value_tokens)
        previous_record_context = _bounded_normalized_context(record_tokens)
    for occurrences in matches.values():
        occurrences.sort()
    return matches, non_luna_failures


def _line_ranges_from_hunks(
    hunks: list[tuple[int, int, int, int]],
) -> list[tuple[int, int | None, int]]:
    if not hunks:
        return [(1, None, 0)]

    ranges: list[tuple[int, int | None, int]] = []
    previous_new = 1
    previous_old = 1
    for old_start, old_count, new_start, new_count in hunks:
        before_new_end = new_start - 1 if new_count else new_start
        before_old_end = old_start - 1 if old_count else old_start
        if (
            before_new_end - previous_new
            != before_old_end - previous_old
        ):
            raise RuntimeError("history parent-child mapping is malformed")
        if before_new_end >= previous_new:
            ranges.append(
                (
                    previous_new,
                    before_new_end,
                    previous_old - previous_new,
                )
            )
        previous_new = new_start + new_count if new_count else new_start + 1
        previous_old = old_start + old_count if old_count else old_start + 1
    ranges.append((previous_new, None, previous_old - previous_new))
    return ranges


def _unchanged_line_ranges_for_path(
    parent: str,
    child: str,
    label: str,
    *,
    root: Path,
) -> list[tuple[int, int | None, int]]:
    return _unchanged_line_ranges_for_commit(
        str(root),
        parent,
        child,
    ).get(label, [(1, None, 0)])


@lru_cache(maxsize=256)
def _unchanged_line_ranges_for_commit(
    root_text: str,
    parent: str,
    child: str,
) -> dict[str, list[tuple[int, int | None, int]]]:
    root = Path(root_text)
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--unified=0",
            "--format=",
            "--no-prefix",
            parent,
            child,
            "--",
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("history parent-child mapping is unavailable")

    hunks_by_path: dict[str, list[tuple[int, int, int, int]]] = {}
    current_path: str | None = None
    for raw_line in result.stdout.splitlines():
        if raw_line.startswith(b"+++ "):
            path = raw_line[4:].decode("utf-8", errors="strict")
            if path == "/dev/null":
                current_path = None
                continue
            current_path = path
            hunks_by_path.setdefault(current_path, [])
            continue
        if current_path is None or not raw_line.startswith(b"@@ "):
            continue
        match = re.match(
            br"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@",
            raw_line,
        )
        if match is None:
            raise RuntimeError("history parent-child mapping is malformed")
        hunks_by_path[current_path].append(
            (
                int(match.group(1)),
                int(match.group(2) or b"1"),
                int(match.group(3)),
                int(match.group(4) or b"1"),
            )
        )
    return {
        path: _line_ranges_from_hunks(hunks)
        for path, hunks in hunks_by_path.items()
    }


def _map_occurrence_span(
    occurrence: tuple[int, int],
    ranges: list[tuple[int, int | None, int]],
) -> tuple[int, int] | None:
    mapped: list[int] = []
    for line_number in range(occurrence[0], occurrence[1] + 1):
        parent_line: int | None = None
        for start, end, offset in ranges:
            if line_number >= start and (end is None or line_number <= end):
                parent_line = line_number + offset
                break
        if parent_line is None:
            return None
        mapped.append(parent_line)
    if not mapped or mapped != list(range(mapped[0], mapped[-1] + 1)):
        return None
    return mapped[0], mapped[-1]


def _occurrence_range_index(
    occurrence: tuple[int, int],
    ranges: list[tuple[int, int | None, int]],
) -> int | None:
    for index, (start, end, _offset) in enumerate(ranges):
        if occurrence[0] >= start and (
            end is None or occurrence[1] <= end
        ):
            return index
    return None


def _inherited_occurrence_indexes(
    rule_id: str,
    after_occurrences: list[tuple[int, int]],
    parent_scans: list[dict[str, list[tuple[int, int]]]],
    parent_ranges: list[list[tuple[int, int | None, int]]],
) -> set[int]:
    used_parent_occurrences = [set() for _ in parent_scans]
    inherited: set[int] = set()
    for after_index, occurrence in enumerate(after_occurrences):
        for parent_index, parent_scan in enumerate(parent_scans):
            mapped = _map_occurrence_span(occurrence, parent_ranges[parent_index])
            if mapped is None:
                continue
            range_index = _occurrence_range_index(
                occurrence,
                parent_ranges[parent_index],
            )
            if range_index is None:
                continue
            if range_index != len(parent_ranges[parent_index]) - 1:
                occurrence_offset = mapped[0] - occurrence[0]
                neighbouring_offsets = {
                    parent_ranges[parent_index][range_index - 1][2]
                    if range_index
                    else None,
                    parent_ranges[parent_index][range_index + 1][2]
                    if range_index + 1 < len(parent_ranges[parent_index])
                    else None,
                }
                if occurrence_offset not in neighbouring_offsets:
                    continue
            for parent_occurrence_index, parent_occurrence in enumerate(
                parent_scan.get(rule_id, ())
            ):
                if parent_occurrence_index in used_parent_occurrences[parent_index]:
                    continue
                if parent_occurrence != mapped:
                    continue
                used_parent_occurrences[parent_index].add(parent_occurrence_index)
                inherited.add(after_index)
                break
            if after_index in inherited:
                break
    return inherited


def luna_history_failures_in_range(
    start: str,
    *,
    end: str = "HEAD",
    root: Path = ROOT,
) -> list[str]:
    """Reject Luna matches newly introduced by any changed commit result."""

    _require_complete_history(root)
    if not _git_commit_exists(root, start) or not _git_commit_exists(root, end):
        raise RuntimeError("Luna history range authority is unavailable")
    if not _is_ancestor(root, start, end):
        raise RuntimeError("Luna history range authority is not an ancestor")
    commits = subprocess.run(
        ["git", "rev-list", "--reverse", f"{start}..{end}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    failures: list[str] = []
    for commit in commits:
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise RuntimeError("Luna history commit authority is malformed")
        parents = _commit_parents(root, commit)
        for label in changed_files_in_commit(commit, root=root):
            after_matches, after_jsonl_findings = _luna_history_blob_scan(
                _git_blob_or_empty(root, commit, label),
                label,
                root=root,
                revision=commit,
            )
            parent_scans = [
                _luna_history_blob_scan(
                    _git_blob_or_empty(root, parent, label),
                    label,
                    root=root,
                    revision=parent,
                )
                for parent in parents
            ]
            before_matches = [scan[0] for scan in parent_scans]
            parent_ranges = (
                [
                    _unchanged_line_ranges_for_path(
                        parent,
                        commit,
                        label,
                        root=root,
                    )
                    for parent in parents
                ]
                if after_matches
                else []
            )
            for rule_id, after_occurrences in sorted(after_matches.items()):
                inherited = _inherited_occurrence_indexes(
                    rule_id,
                    after_occurrences,
                    before_matches,
                    parent_ranges,
                )
                new_indexes = [
                    index
                    for index in range(len(after_occurrences))
                    if index not in inherited
                ]
                allowed_indexes: set[int] = set()
                consumed_exceptions: set[tuple[str, str, int, str]] = set()
                for index in new_indexes:
                    start_line, _end_line = after_occurrences[index]
                    exception = (commit, label, start_line, rule_id)
                    if (
                        exception in LUNA_TDD_HISTORY_ALLOWED_MATCHES
                        and exception not in consumed_exceptions
                    ):
                        allowed_indexes.add(index)
                        consumed_exceptions.add(exception)
                for index in new_indexes:
                    if index in allowed_indexes:
                        continue
                    start_line, _end_line = after_occurrences[index]
                    failures.append(
                        f"commit:{commit[:12]}:{label}:line-{start_line}: "
                        f"forbidden ledger identity token [{rule_id}]"
                    )
            if label.casefold().endswith(".jsonl"):
                failures.extend(
                    _jsonl_finding_surplus(
                        after_jsonl_findings,
                        (scan[1] for scan in parent_scans),
                    )
                )
    return failures


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


def _git_blob_or_empty(root: Path, revision: str | None, relative_path: str) -> bytes:
    if revision is None:
        return b""
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    if not _git_commit_exists(root, revision):
        raise RuntimeError("history authority commit is unavailable")
    return b""


def _git_revision_blob_is_binary(
    root: Path,
    revision: str | None,
    relative_path: str,
) -> bool:
    if revision is None:
        return False
    result = subprocess.run(
        [
            "git",
            "diff",
            "--numstat",
            "--no-renames",
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            revision,
            "--",
            relative_path,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("history authority blob type is unavailable")
    lines = result.stdout.splitlines()
    if not lines:
        return False
    fields = lines[0].split("\t", 2)
    if len(fields) != 3:
        raise RuntimeError("history authority blob type is malformed")
    return fields[0] == "-" and fields[1] == "-"


def _decode_luna_history_blob(raw: bytes) -> str:
    if len(raw) > MAX_TEXT_BYTES:
        raise RuntimeError("Luna history authority exceeds text limit")
    if b"\0" in raw:
        raise RuntimeError("Luna history authority is not text")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RuntimeError("Luna history authority blob is not strict UTF-8") from error


def _luna_match_lines_by_rule(text: str) -> dict[str, list[int]]:
    return {
        rule_id: [start_line for start_line, _end_line in spans]
        for rule_id, spans in _luna_match_occurrence_spans_by_rule(text).items()
    }


def _luna_match_occurrence_spans_by_rule(
    text: str,
) -> dict[str, list[tuple[int, int]]]:
    matches: dict[str, list[tuple[int, int]]] = {}
    for rule_id, start_line, _end_line in _iter_normalized_identity_line_spans(
        text,
        LUNA_SEQUENCES_BY_FIRST_TOKEN,
    ):
        matches.setdefault(rule_id, []).append((start_line, _end_line))
    return matches


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


def luna_history_start(
    root: Path,
    manifest: Mapping[str, Any],
) -> tuple[str, str]:
    """Select prospective Luna history in PR, squash-main, or isolated fixtures."""

    _require_complete_history(root)
    if _git_commit_exists(root, LUNA_RED_PROOF_COMMIT) and _is_ancestor(
        root,
        LUNA_RED_PROOF_COMMIT,
    ):
        return LUNA_RED_PROOF_COMMIT, "pr-descendant"
    if _git_commit_exists(root, LUNA_HISTORY_BASE) and _is_ancestor(
        root,
        LUNA_HISTORY_BASE,
    ):
        return LUNA_HISTORY_BASE, "canonical-main-squash"
    start, _mode = unicode_history_start(root, manifest)
    return start, "isolated-authority-fallback"


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
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        label = relative.as_posix()
        if label.casefold().endswith(".jsonl"):
            failures.extend(scan_jsonl(path, root=root))
            continue
        text = decode_text(path)
        if text is None:
            continue
        prepared, policy_failures = prepare_tracked_text(label, text)
        failures.extend(
            scan_public_text(
                label,
                text,
                generic_text=prepared,
                policy_failures=policy_failures,
            )
        )

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
                include_luna_execution_settings=False,
            )
        )

    luna_start, _mode = luna_history_start(root, manifest)
    failures.extend(luna_history_failures_in_range(luna_start, root=root))

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
