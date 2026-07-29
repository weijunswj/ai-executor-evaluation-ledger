import json
import hashlib
import os
import re
from typing import Dict, Any, List, Tuple

REASONING_KEYS = {
    "requested_reasoning_level",
    "observed_reasoning_mode",
    "thinking_setting",
    "native_reasoning_classification",
    "reasoning_exposure_status",
    "reasoning_grouping"
}

ALLOWED_PROVIDERS = {"Google", "DeepSeek", "Qwen", "Anthropic", "OpenAI", "MiMo"}
ALLOWED_MODELS = {"MiMo 2.5 Pro", "Claude Opus 4.8", "Claude Opus 5", "DeepSeek V4 Pro", "GPT-5.6 Sol", "Qwen3.7 Plus", "Gemini 3.6 Flash"}
UUID_PATTERN = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")

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

def parse_intake_comment(comment_id: int, body: str, recorded_run_ids: set, seen_candidate_ids: set) -> Tuple[str, Dict[str, Any], str]:
    """
    Parses a single #142 intake comment fail-closed.
    Returns (disposition, payload, reason_or_error).
    Dispositions:
      'admitted', 'already_recorded', 'duplicate', 'malformed', 'conflicted',
      'non_evaluable', 'owner_withdrawn', 'ineligible', 'blocked_controller_action'
    """
    body_bytes = body.encode('utf-8')
    body_sha256 = hashlib.sha256(body_bytes).hexdigest()

    # Special handling for explicitly withdrawn comment under #150
    if comment_id == 5088187239:
        return "owner_withdrawn", {}, "Owner withdrawn under issue #150 (Qwen3.6 Plus intake)"

    # Byte zero marker enforcement
    if not body.startswith("<!-- ledger-intake:v1 -->"):
        return "malformed", {}, "Missing or invalid byte-zero intake marker"

    # Remove marker and leading whitespace/newlines
    payload_str = body[len("<!-- ledger-intake:v1 -->"):].strip()
    if not payload_str:
        return "malformed", {}, "Empty intake payload"

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as e:
        return "malformed", {}, f"Invalid JSON payload: {str(e)}"

    if not isinstance(payload, dict):
        return "malformed", {}, "Payload must be a JSON object"

    # Check for prohibited UUIDs in intake payload
    if UUID_PATTERN.search(payload_str):
        return "ineligible", payload, "Intake payload contains UUID which fails public safety policy"

    # Check for prohibited reasoning metadata at any nesting level
    if contains_reasoning_keys(payload):
        return "malformed", {}, "Payload contains prohibited reasoning metadata"

    # Schema validation
    required_fields = [
        "schema_version", "record_type", "controller_run_id", "evaluation_run_id",
        "provider", "canonical_base_model", "evaluation_protocol", "repository_alias",
        "issue_number", "source_revision", "task_class", "difficulty", "verdict",
        "score_dimensions", "weighted_score_5", "public_safe_evidence", "secret_exposure_status"
    ]
    for field in required_fields:
        if field not in payload:
            return "malformed", {}, f"Missing required field: {field}"

    if payload.get("schema_version") != 1 or payload.get("record_type") != "evaluation_intake":
        return "malformed", {}, "Invalid schema_version or record_type"

    run_id = payload.get("evaluation_run_id")
    if not run_id:
        return "malformed", {}, "Missing evaluation_run_id"

    # Check if already recorded in canonical history
    if run_id in recorded_run_ids:
        return "already_recorded", payload, "Already recorded in canonical history"

    # Check for duplicate within queue intake batch
    if run_id in seen_candidate_ids:
        return "duplicate", payload, "Duplicate intake in queue"

    # Model and provider authority check
    provider = payload.get("provider")
    model = payload.get("canonical_base_model")
    if model not in ALLOWED_MODELS:
        return "ineligible", payload, f"Unsupported model mapping: {model}"

    # Secret exposure check
    if payload.get("secret_exposure_status") != "none":
        return "blocked_controller_action", payload, "Possible or confirmed secret exposure"

    # Evaluation protocol check
    protocol = payload.get("evaluation_protocol")
    if protocol not in ["gated_v1", "legacy_pre_gate", "protocol_unknown"]:
        return "malformed", payload, f"Invalid evaluation_protocol: {protocol}"

    return "admitted", payload, "Valid candidate intake admitted"
