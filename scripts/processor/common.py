"""Shared closed-contract helpers for the integrated Ledger processor."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable

GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
SAFE_AUTHOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}(?:\[bot\])?$")

AUTHORIZED_PAIRS = frozenset(
    {
        ("Xiaomi", "MiMo 2.5 Pro"),
        ("MiMo", "MiMo 2.5 Pro"),
        ("Anthropic", "Claude Opus 5"),
        ("DeepSeek", "DeepSeek V4 Pro"),
        ("OpenAI", "GPT-5.6 Sol"),
        ("Qwen", "Qwen3.7 Plus"),
        ("Google", "Gemini 3.1 Pro"),
        ("MiniMax", "MiniMax M3"),
    }
)

WITHDRAWN_PAIRS = frozenset({("Anthropic", "Claude Opus 4.8")})
INELIGIBLE_PAIRS = frozenset({("Qwen", "Qwen3.6 Plus")})

MODEL_ALIASES = {
    "Mimo 2.5 Pro": "MiMo 2.5 Pro",
    "Qwen 3.6 Plus": "Qwen3.6 Plus",
}

REASONING_KEYS = frozenset(
    {
        "requested_reasoning_level",
        "observed_reasoning_mode",
        "thinking_setting",
        "native_reasoning_classification",
        "reasoning_exposure_status",
        "reasoning_grouping",
        "reasoning_level",
        "reasoning_mode",
    }
)

SELF_GRADING_KEYS = frozenset(
    {
        "executor_self_grading",
        "self_score",
        "self_assessed_score",
        "executor_verdict",
        "executor_evaluation",
    }
)

PROHIBITED_IDENTITY_KEYS = frozenset(
    {
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
    }
)

UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\b(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^ \t\r\n]+"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/\s]+"),
    re.compile(r"(?i)(?:^|[\s\"'])(?:/home|/Users)/[^/\s\"']+"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"(?i)https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|[^/\s.]+\.(?:internal|local))(?:[:/]|$)"),
    UUID_PATTERN,
    re.compile(r"(?i)[?&](?:token|api_key|apikey|secret|password|key)=[^&\s]+"),
    re.compile(
        r"(?ix)\b(?:token|api[_-]?key|secret|password|passwd|connection[_-]?string)\b"
        r"\s*[:=]\s*[\"'](?!REDACTED|PLACEHOLDER|EXAMPLE|CHANGEME)[^\"']{8,}[\"']"
    ),
)

GENERIC_DISPOSITION_CODES = frozenset(
    {
        "already_recorded",
        "authority_missing",
        "conflicting_identity",
        "duplicate_identity",
        "ineligible_identity",
        "invalid_schema",
        "no_marker",
        "receipt_conflict",
        "source_changed",
        "unsafe_content",
        "unsupported_identity",
        "withdrawn_identity",
    }
)


class ProcessorError(RuntimeError):
    """A public-safe processor failure containing only a bounded code."""

    def __init__(self, code: str):
        if code not in GENERIC_DISPOSITION_CODES and not code.startswith("processor_"):
            code = "processor_failure"
        self.code = code
        super().__init__(code)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one deterministic UTF-8 representation used by receipts."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_line_bytes(value: Any) -> bytes:
    """Return the exact JSONL record bytes, including the LF delimiter."""

    return canonical_json_bytes(value) + b"\n"


def valid_git_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(GIT_SHA_PATTERN.fullmatch(value))


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.fullmatch(value))


def valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_IDENTIFIER_PATTERN.fullmatch(value))


def valid_author_login(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_AUTHOR_PATTERN.fullmatch(value))


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def normalize_known_model(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return MODEL_ALIASES.get(value, value)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(key)
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def find_unsafe_content(value: Any) -> bool:
    for text in iter_strings(value):
        if "\x00" in text or any(ord(char) < 9 for char in text):
            return True
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            return True
    return False


def has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in REASONING_KEYS or key in SELF_GRADING_KEYS or key in PROHIBITED_IDENTITY_KEYS:
                return True
            if has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(has_forbidden_key(child) for child in value)
    return False


def safe_comment_body_hash(body: str) -> str:
    return sha256_bytes(body.encode("utf-8"))


def safe_author_hash(login: Any) -> str:
    if not isinstance(login, str):
        return sha256_bytes(b"")
    return sha256_bytes(login.encode("utf-8"))


def validate_batch_receipt_closure(value: Any) -> bool:
    """Check the count, map, binding and terminal-outcome relationships in a v2 batch."""

    if not isinstance(value, dict) or value.get("schema_version") != 2 or value.get("receipt_type") != "batch":
        return False
    source_ids = value.get("source_comment_ids")
    source_hashes = value.get("source_body_sha256")
    selected_ids = value.get("selected_comment_ids")
    terminal = value.get("terminal_outcomes")
    bindings = value.get("comment_bindings")
    admitted = value.get("admitted_run_ids")
    proofs = value.get("accepted_record_proofs")
    record_hashes = value.get("canonical_record_hashes")
    if not all(isinstance(item, list) for item in (source_ids, selected_ids, bindings, admitted)):
        return False
    if not isinstance(source_hashes, dict) or not isinstance(terminal, dict) or not isinstance(proofs, dict) or not isinstance(record_hashes, dict):
        return False
    if any(not isinstance(item, str) for item in admitted):
        return False
    if len(admitted) != len(set(admitted)):
        return False
    if any(not isinstance(item, int) or item <= 0 for item in source_ids + selected_ids):
        return False
    if len(source_ids) != len(set(source_ids)) or len(selected_ids) != len(set(selected_ids)):
        return False
    source_set = set(source_ids)
    selected_set = set(selected_ids)
    if source_ids != sorted(source_ids) or selected_ids != sorted(selected_ids):
        return False
    if not selected_set.issubset(source_set):
        return False
    if value.get("full_queue_count") != len(source_ids):
        return False
    if value.get("selected_comment_count") != len(selected_ids):
        return False
    if value.get("terminal_outcome_count") != len(terminal):
        return False
    if set(source_hashes) != {str(item) for item in source_ids}:
        return False
    if set(terminal) != {str(item) for item in selected_ids}:
        return False
    if value.get("latest_observed_comment_id") != (max(source_ids) if source_ids else None):
        return False
    binding_by_id: dict[int, dict[str, Any]] = {}
    for binding in bindings:
        if not isinstance(binding, dict) or not isinstance(binding.get("comment_id"), int):
            return False
        comment_id = binding["comment_id"]
        if comment_id in binding_by_id:
            return False
        binding_by_id[comment_id] = binding
    if set(binding_by_id) != source_set:
        return False
    if [binding.get("comment_id") for binding in bindings] != source_ids:
        return False
    fingerprints = [
        {
            "id": comment_id,
            "author_sha256": binding_by_id[comment_id].get("author_sha256"),
            "created_at": binding_by_id[comment_id].get("created_at"),
            "updated_at": binding_by_id[comment_id].get("updated_at"),
            "body_sha256": binding_by_id[comment_id].get("body_sha256"),
        }
        for comment_id in sorted(source_set)
    ]
    if value.get("queue_snapshot_sha256") != sha256_bytes(canonical_json_bytes(fingerprints)):
        return False
    expected_latest_update = max(
        (item["updated_at"] for item in fingerprints if isinstance(item["updated_at"], str)),
        default=None,
    )
    if value.get("latest_observed_update_time") != expected_latest_update:
        return False
    if set(record_hashes) != set(admitted):
        return False
    if set(proofs) != set(admitted):
        return False
    admitted_set = set(admitted)
    for comment_id in selected_ids:
        outcome = terminal.get(str(comment_id))
        binding = binding_by_id.get(comment_id)
        if not isinstance(outcome, dict) or not isinstance(binding, dict):
            return False
        for field in ("outcome_code", "evaluation_run_id", "canonical_record_sha256", "cleanup_eligible"):
            if outcome.get(field) != binding.get(field):
                return False
        if outcome.get("outcome_code") == "admitted":
            run_id = outcome.get("evaluation_run_id")
            if run_id not in admitted_set or outcome.get("canonical_record_sha256") != record_hashes.get(run_id):
                return False
        elif outcome.get("evaluation_run_id") is not None or outcome.get("canonical_record_sha256") is not None:
            return False
    return True
