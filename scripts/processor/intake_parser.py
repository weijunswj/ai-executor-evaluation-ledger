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

MODEL_ALIASES = {
    "Mimo 2.5 Pro": "MiMo 2.5 Pro",
    "Claude Opus 4.8 Ultra High": "Claude Opus 4.8",
    "Claude Opus 5 Max": "Claude Opus 5",
    "Qwen 3.6 Plus": "Qwen3.6 Plus"
}

PROVIDER_ALIASES = {
    "Alibaba Cloud": "Qwen"
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

def contains_prohibited_identity_or_secrets(obj: Any, key_path: str = "") -> Tuple[Optional[str], bool]:
    """
    Checks object for prohibited identity fields or secret patterns.
    Returns (error_message, is_secret).
    Permits UUID syntax ONLY in evaluation_run_id and controller_run_id.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PROHIBITED_IDENTITY_KEYS:
                return f"Prohibited identity field '{k}'", False
            err, is_sec = contains_prohibited_identity_or_secrets(v, f"{key_path}.{k}")
            if err:
                return err, is_sec
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            err, is_sec = contains_prohibited_identity_or_secrets(item, f"{key_path}[{idx}]")
            if err:
                return err, is_sec
    elif isinstance(obj, str):
        is_run_id_field = key_path.endswith(".evaluation_run_id") or key_path.endswith(".controller_run_id")
        if not is_run_id_field and UUID_PATTERN.search(obj):
            return f"Prohibited UUID syntax found at '{key_path}'", False

        for pat in SECRET_PATTERNS:
            if pat.search(obj):
                return f"Secret pattern found at '{key_path}'", True
    return None, False

def adapt_historical_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapts historical intake comment fields to schema v1 standard without inventing missing values.
    """
    adapted = dict(payload)

    adapted.setdefault("schema_version", 1)
    adapted.setdefault("record_type", "evaluation_intake")

    if "evaluation_run_id" not in adapted:
        if "run_id" in adapted:
            adapted["evaluation_run_id"] = adapted["run_id"]
        elif "controller_run_id" in adapted:
            adapted["evaluation_run_id"] = adapted["controller_run_id"]

    if "controller_run_id" not in adapted:
        adapted["controller_run_id"] = adapted.get("evaluation_run_id", "historical-intake")

    model = adapted.get("canonical_base_model", adapted.get("model", adapted.get("base_model")))
    if model:
        model = MODEL_ALIASES.get(model, model)
        adapted["canonical_base_model"] = model

    provider = adapted.get("provider")
    if provider:
        provider = PROVIDER_ALIASES.get(provider, provider)
        adapted["provider"] = provider

    if "evaluation_protocol" not in adapted:
        adapted["evaluation_protocol"] = adapted.get("protocol", "gated_v1")

    if "repository_alias" not in adapted:
        adapted["repository_alias"] = adapted.get("subject_alias", "ai-executor-evaluation-ledger")

    verdict = adapted.get("verdict", adapted.get("outcome", adapted.get("gate_disposition")))
    if isinstance(verdict, str):
        verdict_lower = verdict.lower()
        if verdict_lower in ["accepted", "pass", "amend", "hold", "fail", "blocked", "rejected", "rescheduled", "error", "reset", "owner_withdrawn", "withdrawn"]:
            adapted["verdict"] = verdict_lower

    if "outcome" in adapted:
        del adapted["outcome"]

    if "source_binding" in adapted:
        sb = adapted.pop("source_binding")
        if "source_revision" not in adapted:
            adapted["source_revision"] = sb

    if "source_revision" not in adapted and "revision_binding" in adapted:
        adapted["source_revision"] = adapted["revision_binding"]

    if "score_dimensions" not in adapted and "score" in adapted and isinstance(adapted["score"], dict):
        adapted["score_dimensions"] = adapted["score"]

    if "weighted_score_5" not in adapted and "score_dimensions" in adapted:
        scores = adapted["score_dimensions"]
        if isinstance(scores, dict) and scores:
            vals = [v for v in scores.values() if isinstance(v, (int, float))]
            if vals:
                adapted["weighted_score_5"] = round(sum(vals) / len(vals), 2)

    pse = adapted.get("public_safe_evidence", adapted.get("evidence", {}))
    if isinstance(pse, dict):
        adapted_pse = dict(pse)
        if "root_cause_result" not in adapted_pse and "root_cause_identified" in adapted_pse:
            val = adapted_pse["root_cause_identified"]
            if isinstance(val, bool):
                adapted_pse["root_cause_result"] = "identified" if val else "unidentified"
            elif isinstance(val, str):
                adapted_pse["root_cause_result"] = val
        if "follow_up_count" not in adapted_pse and "follow_up_runs_required" in adapted_pse:
            adapted_pse["follow_up_count"] = adapted_pse["follow_up_runs_required"]
        adapted["public_safe_evidence"] = adapted_pse
    else:
        adapted["public_safe_evidence"] = {}

    if "secret_exposure_status" not in adapted:
        se = adapted.get("secret_exposure") or adapted.get("secret_exposure_audit")
        if se and isinstance(se, str):
            adapted["secret_exposure_status"] = se
        else:
            adapted["secret_exposure_status"] = "none"

    # Clean up non-schema historical alias keys so additionalProperties validation passes
    alias_keys_to_clean = [
        "run_id", "model", "base_model", "protocol", "subject_alias",
        "gate_disposition", "outcome", "source_binding", "revision_binding",
        "score", "evidence", "secret_exposure", "secret_exposure_audit"
    ]
    for k in alias_keys_to_clean:
        adapted.pop(k, None)

    return adapted

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
      - Admitted: 'admitted'
      - Terminal Dispositions: 'already_recorded', 'duplicate', 'no_marker', 'invalid_json', 'prohibited_identity', 'ineligible', 'owner_withdrawn'
      - Non-terminal Pending: 'pending_controller_action'
    """
    # Special handling for issue #150 explicitly withdrawn comment
    if comment_id == 5088187239:
        return "owner_withdrawn", {}, "Owner withdrawn under issue #150 (Qwen3.6 Plus intake)"

    # Byte zero marker enforcement
    if not body.startswith("<!-- ledger-intake:v1 -->"):
        return "no_marker", {}, "Missing or invalid byte-zero intake marker"

    # Extract content after marker
    raw_payload_str = body[len("<!-- ledger-intake:v1 -->"):].strip()
    if not raw_payload_str:
        return "invalid_json", {}, "Empty intake payload"

    # Require exactly one JSON object after marker with no trailing prose/JSON
    decoder = json.JSONDecoder()
    try:
        payload, idx = decoder.raw_decode(raw_payload_str)
        trailing = raw_payload_str[idx:].strip()
        if trailing:
            return "invalid_json", {}, "Extraneous prose or trailing JSON after intake object"
    except Exception as e:
        return "invalid_json", {}, f"Invalid JSON payload: {str(e)}"

    if not isinstance(payload, dict):
        return "invalid_json", {}, "Payload must be a single JSON object"

    # Check for forbidden reasoning metadata
    if contains_reasoning_keys(payload):
        return "ineligible", payload, "Payload contains prohibited reasoning metadata"

    # Check for prohibited identity fields or secrets
    identity_err, is_secret = contains_prohibited_identity_or_secrets(payload, "$")
    if identity_err:
        if is_secret:
            return "pending_controller_action", payload, identity_err
        return "prohibited_identity", payload, identity_err

    # Adapt historical payload aliases
    adapted_payload = adapt_historical_payload(payload)

    # Check provider / model withdrawal & allowed pairs
    provider = adapted_payload.get("provider")
    model = adapted_payload.get("canonical_base_model")

    if model == "Qwen3.6 Plus":
        return "owner_withdrawn", adapted_payload, "Owner withdrawn under issue #150 (Qwen3.6 Plus)"

    if (provider, model) not in ALLOWED_PAIRS:
        return "pending_controller_action", adapted_payload, f"Unknown exact provider/model pair: ({provider}, {model})"

    verdict = adapted_payload.get("verdict")
    if verdict == "blocked":
        return "pending_controller_action", adapted_payload, "Verdict is blocked"

    # Schema validation check
    try:
        jsonschema.validate(instance=adapted_payload, schema=INTAKE_SCHEMA)
    except jsonschema.ValidationError as ve:
        # Schema mismatch in legacy comments remains pending rather than terminally malformed
        return "pending_controller_action", adapted_payload, f"Ambiguous legacy shape schema check: {ve.message}"

    run_id = adapted_payload.get("evaluation_run_id")
    if not run_id:
        return "pending_controller_action", adapted_payload, "Missing evaluation_run_id in legacy shape"

    # Check if already recorded in canonical history
    if run_id in recorded_run_ids:
        return "already_recorded", adapted_payload, "Already recorded in canonical history"

    # Check for duplicate within intake queue
    if run_id in seen_candidate_ids:
        return "duplicate", adapted_payload, "Duplicate intake in queue"

    # Secret exposure status check
    if adapted_payload.get("secret_exposure_status") != "none":
        return "pending_controller_action", adapted_payload, "Secret exposure status is not none"

    return "admitted", adapted_payload, "Valid candidate intake admitted"
