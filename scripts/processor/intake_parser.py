import json
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set
import jsonschema

ROOT = Path(__file__).resolve().parents[2]
INTAKE_SCHEMA_PATH = ROOT / "schema" / "intake.schema.json"

with open(INTAKE_SCHEMA_PATH, "r", encoding="utf-8") as f:
    INTAKE_SCHEMA = json.load(f)

REASONING_KEYS = {
    "requested_reasoning_level",
    "observed_reasoning_mode",
    "thinking_setting",
    "native_reasoning_classification",
    "reasoning_exposure_status",
    "reasoning_grouping"
}

PROHIBITED_IDENTITY_KEYS = {
    "owner", "username", "login", "email", "user_id", "owner_id",
    "workspace_uuid", "project_ref", "project_id", "application_uuid",
    "deployment_uuid", "client_id", "support_case", "support_case_id"
}

ALLOWED_PAIRS = {
    ("Xiaomi", "MiMo 2.5 Pro"),
    ("MiMo", "MiMo 2.5 Pro"),
    ("Anthropic", "Claude Opus 4.8"),
    ("Anthropic", "Claude Opus 5"),
    ("DeepSeek", "DeepSeek V4 Pro"),
    ("OpenAI", "GPT-5.6 Sol"),
    ("Qwen", "Qwen3.7 Plus"),
    ("Google", "Gemini 3.1 Pro"),
    ("Google", "Gemini 3.6 Flash"),
    ("MiniMax", "MiniMax M3"),
    ("Qwen", "Qwen3.6 Plus")  # Identifiable for #150 withdrawal
}

UUID_PATTERN = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
]

def contains_reasoning_keys(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in REASONING_KEYS:
                return True
            if contains_reasoning_keys(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if contains_reasoning_keys(item):
                return True
    return False

def contains_prohibited_identity_or_secrets(obj: Any, key_path: str = "") -> Optional[str]:
    """
    Checks object for prohibited identity fields or secrets.
    Permits UUID syntax ONLY in evaluation_run_id and controller_run_id.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PROHIBITED_IDENTITY_KEYS:
                return f"Prohibited identity field '{k}'"
            err = contains_prohibited_identity_or_secrets(v, f"{key_path}.{k}")
            if err:
                return err
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            err = contains_prohibited_identity_or_secrets(item, f"{key_path}[{idx}]")
            if err:
                return err
    elif isinstance(obj, str):
        # Allow UUID in run IDs
        is_run_id_field = key_path.endswith(".evaluation_run_id") or key_path.endswith(".controller_run_id")
        if not is_run_id_field and UUID_PATTERN.search(obj):
            return f"Prohibited UUID syntax found at '{key_path}'"

        for pat in SECRET_PATTERNS:
            if pat.search(obj):
                return f"Secret pattern found at '{key_path}'"
    return None

def parse_intake_comment(
    comment_id: int,
    body: str,
    recorded_run_ids: Set[str],
    seen_candidate_ids: Set[str]
) -> Tuple[str, Dict[str, Any], str]:
    """
    Parses a single intake comment.
    Returns (disposition, payload, reason).
    Dispositions:
      'admitted', 'already_recorded', 'duplicate', 'malformed', 'conflicted',
      'non_evaluable', 'owner_withdrawn', 'ineligible', 'blocked_controller_action'
    """
    # Special handling for issue #150 explicitly withdrawn comment
    if comment_id == 5088187239:
        return "owner_withdrawn", {}, "Owner withdrawn under issue #150 (Qwen3.6 Plus intake)"

    # Byte zero marker enforcement
    if not body.startswith("<!-- ledger-intake:v1 -->"):
        return "malformed", {}, "Missing or invalid byte-zero intake marker"

    # Extract content after marker
    raw_payload_str = body[len("<!-- ledger-intake:v1 -->"):].strip()
    if not raw_payload_str:
        return "malformed", {}, "Empty intake payload"

    # Require exactly one JSON object after marker with no trailing prose/JSON
    decoder = json.JSONDecoder()
    try:
        payload, idx = decoder.raw_decode(raw_payload_str)
        trailing = raw_payload_str[idx:].strip()
        if trailing:
            return "malformed", {}, "Extraneous prose or trailing JSON after intake object"
    except Exception as e:
        return "malformed", {}, f"Invalid JSON payload: {str(e)}"

    if not isinstance(payload, dict):
        return "malformed", {}, "Payload must be a single JSON object"

    # Check for forbidden reasoning metadata
    if contains_reasoning_keys(payload):
        return "malformed", {}, "Payload contains prohibited reasoning metadata"

    # Check for prohibited identity fields or secrets
    identity_err = contains_prohibited_identity_or_secrets(payload, "$")
    if identity_err:
        return "ineligible", payload, identity_err

    # Draft 2020-12 schema validation
    try:
        jsonschema.validate(instance=payload, schema=INTAKE_SCHEMA)
    except jsonschema.ValidationError as ve:
        return "malformed", payload, f"Schema validation failed: {ve.message}"

    run_id = payload.get("evaluation_run_id")
    if not run_id:
        return "malformed", payload, "Missing evaluation_run_id"

    # Check if already recorded in canonical history
    if run_id in recorded_run_ids:
        return "already_recorded", payload, "Already recorded in canonical history"

    # Check for duplicate within intake queue
    if run_id in seen_candidate_ids:
        return "duplicate", payload, "Duplicate intake in queue"

    # Provider / model pairing check
    provider = payload.get("provider")
    model = payload.get("canonical_base_model")
    if (provider, model) not in ALLOWED_PAIRS:
        return "blocked_controller_action", payload, f"Unknown exact provider/model pair: ({provider}, {model})"

    # Secret exposure status
    if payload.get("secret_exposure_status") != "none":
        return "blocked_controller_action", payload, "Secret exposure status is not none"

    return "admitted", payload, "Valid candidate intake admitted"
