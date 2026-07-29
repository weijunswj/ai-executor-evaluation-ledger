import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional, Set
import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.processor.intake_parser import parse_intake_comment
from scripts.rebuild_views import rebuild_views
from scripts.check_public_safety import main as audit_public_safety_main

LEDGER_PATH = ROOT / "evaluations.jsonl"
DISPOSITIONS_PATH = ROOT / "ledger" / "dispositions.jsonl"
BATCH_RECEIPTS_DIR = ROOT / "ledger" / "receipts" / "batches"
EVALUATION_SCHEMA_PATH = ROOT / "schema" / "evaluation.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
DISPOSITION_SCHEMA_PATH = ROOT / "schema" / "disposition.schema.json"

with open(EVALUATION_SCHEMA_PATH, "r", encoding="utf-8") as f:
    EVALUATION_SCHEMA = json.load(f)
with open(RECEIPT_SCHEMA_PATH, "r", encoding="utf-8") as f:
    RECEIPT_SCHEMA = json.load(f)
with open(DISPOSITION_SCHEMA_PATH, "r", encoding="utf-8") as f:
    DISPOSITION_SCHEMA = json.load(f)

WITHDRAWN_BASE_RUN_IDS = {
    "2026-07-24-claude-opus-4-8-business-automation-a-implementation-001",
    "2026-07-24-claude-opus-4-8-business-automation-a-amendment-001",
    "2026-07-24-correction-claude-opus-4-8-high-implementation-001",
    "2026-07-24-correction-claude-opus-4-8-high-amendment-001",
    "2026-07-24-claude-opus-4-8-high-business-automation-a-amendment-002",
    "2026-07-24-claude-opus-4-8-ultra-high-business-automation-a-amendment-003",
    "2026-07-25-correction-mimo-2-5-pro-default-provenance-repair-003"
}

@dataclass
class ProcessBatchConfig:
    operating_mode: str = "initial"  # "initial" or "incremental"
    base_sha: str = "27748b1fa4b70eb69f18047c31ec97c3505beb88"
    batch_id: str = "batch-20260729-gate3-amendment-004"
    controller_authority: str = "2026-07-29-ledger-integrated-processor-gate3-amendment-004"
    pr_number: int = 151
    dry_run: bool = False

def fetch_live_142_comments() -> List[Dict[str, Any]]:
    cmd = ["gh", "api", "repos/weijunswj/ai-executor-evaluation-ledger/issues/142/comments", "--paginate"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch #142 comments: {res.stderr}")
    return json.loads(res.stdout)

def fetch_single_comment(comment_id: int) -> Dict[str, Any]:
    cmd = ["gh", "api", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to re-fetch comment {comment_id}: {res.stderr}")
    return json.loads(res.stdout)

def fetch_issue_metadata() -> Dict[str, Any]:
    cmd = ["gh", "api", "repos/weijunswj/ai-executor-evaluation-ledger/issues/142"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch issue #142 metadata: {res.stderr}")
    return json.loads(res.stdout)

def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def load_canonical_base_records(base_sha: str) -> List[Dict[str, Any]]:
    """
    Initial Mode: Loads evaluations.jsonl from original migration base commit,
    applies schema v2 migration, excludes 6 #150 withdrawals and 1 reasoning correction.
    Returns preserved canonical base records.
    """
    cmd = ["git", "show", f"{base_sha}:evaluations.jsonl"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to read base evaluations.jsonl from {base_sha}: {res.stderr}")

    records = []
    forbidden_keys = {
        "requested_reasoning_level", "observed_reasoning_mode",
        "thinking_setting", "native_reasoning_classification",
        "reasoning_exposure_status", "reasoning_grouping"
    }

    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        run_id = rec.get("run_id")
        if run_id in WITHDRAWN_BASE_RUN_IDS:
            continue

        # Scrub reasoning fields
        for k in list(rec.keys()):
            if k in forbidden_keys:
                del rec[k]

        # Model canonicalization
        model = rec.get("model")
        if model == "Claude Opus 4.8 Ultra High":
            rec["model"] = "Claude Opus 4.8"
        elif model == "Claude Opus 5 Max":
            rec["model"] = "Claude Opus 5"
        elif model == "Mimo 2.5 Pro":
            rec["model"] = "MiMo 2.5 Pro"

        if "evaluation_protocol" not in rec:
            rec["evaluation_protocol"] = "protocol_unknown"

        rec["schema_version"] = 2
        records.append(rec)

    return records

def load_canonical_main_records() -> List[Dict[str, Any]]:
    """
    Incremental Mode: Reads evaluations.jsonl from checked-out canonical main.
    Preserves every existing canonical record without re-migrating.
    """
    if not LEDGER_PATH.exists():
        return []
    records = []
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def process_batch(config: Optional[ProcessBatchConfig] = None) -> Dict[str, Any]:
    if config is None:
        config = ProcessBatchConfig()

    # Immutable receipt collision check in Incremental Mode
    BATCH_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    target_receipt_path = BATCH_RECEIPTS_DIR / f"{config.batch_id}.json"
    if config.operating_mode == "incremental" and target_receipt_path.exists():
        raise ValueError(f"Duplicate batch ID collision: {config.batch_id} already exists in canonical receipts")

    # Load canonical baseline records according to operating mode
    if config.operating_mode == "initial":
        preserved_base_records = load_canonical_base_records(config.base_sha)
    else:
        preserved_base_records = load_canonical_main_records()

    recorded_run_ids = {r.get("run_id") for r in preserved_base_records}

    # 1. Snapshot 1: Fetch live queue comments & issue metadata
    comments_snap1 = fetch_live_142_comments()
    issue_meta1 = fetch_issue_metadata()

    full_queue_count = len(comments_snap1)
    max_comment_id = max((c["id"] for c in comments_snap1), default=0)
    max_updated_at = max((c["updated_at"] for c in comments_snap1), default="2026-07-29T00:00:00Z")

    snap1_canon_str = json.dumps([{
        "id": c["id"],
        "user": c.get("user", {}).get("login"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "body_sha256": compute_sha256(c.get("body", "").encode("utf-8"))
    } for c in comments_snap1], sort_keys=True)
    snap1_hash = compute_sha256(snap1_canon_str.encode("utf-8"))

    snap1_comment_hashes = {}
    for c in comments_snap1:
        cid = c["id"]
        body = c.get("body", "")
        snap1_comment_hashes[cid] = compute_sha256(body.encode("utf-8"))

    seen_candidate_ids = set()
    admitted_records = []
    admitted_run_ids = []
    source_comment_ids = []
    terminal_dispositions = {}
    disposition_records = []
    pending_items = []
    cleanup_candidates = []
    comment_bindings = []

    # Parse and classify each comment
    for c in comments_snap1:
        cid = c["id"]
        author = c.get("user", {}).get("login")
        created_at = c.get("created_at")
        updated_at = c.get("updated_at")
        body = c.get("body", "")
        body_sha = snap1_comment_hashes[cid]

        disp, payload, reason = parse_intake_comment(cid, body, recorded_run_ids, seen_candidate_ids)

        if disp == "admitted":
            run_id = payload["evaluation_run_id"]
            seen_candidate_ids.add(run_id)
            admitted_run_ids.append(run_id)
            source_comment_ids.append(cid)
            cleanup_candidates.append(cid)

            pse = payload.get("public_safe_evidence", {})
            out_rec = {
                "schema_version": 2,
                "record_type": "evaluation",
                "run_id": run_id,
                "reviewed_at": payload.get("reviewed_at") or created_at,
                "executor_reported_at": payload.get("executor_reported_at"),
                "provider": payload.get("provider"),
                "model": payload.get("canonical_base_model"),
                "evaluation_protocol": payload.get("evaluation_protocol", "gated_v1"),
                "task_class": payload.get("task_class", "general-capability"),
                "difficulty": payload.get("difficulty", "medium"),
                "subject_alias": payload.get("repository_alias", "ai-executor-evaluation-ledger"),
                "revision_binding": payload.get("source_revision") or payload.get("revision_binding") or "exact repository commit",
                "prompt_sha256": payload.get("prompt_sha256"),
                "outcome": payload.get("outcome") or payload.get("verdict") or "accepted",
                "first_pass_accepted": pse.get("first_pass_accepted", False),
                "controller_intervention_required": pse.get("controller_intervention_required", False),
                "safe_final_state_reported": pse.get("safe_final_state_reported"),
                "safe_final_state_verified": pse.get("safe_final_state_verified"),
                "root_cause_identified": pse.get("root_cause_identified"),
                "root_cause_result": pse.get("root_cause_result"),
                "follow_up_runs_required": pse.get("follow_up_runs_required") or pse.get("follow_up_count"),
                "follow_up_count": pse.get("follow_up_count") or pse.get("follow_up_runs_required"),
                "scores": payload.get("score_dimensions", {}),
                "weighted_score_5": payload.get("weighted_score_5", 0.0),
                "weighted_score_10": round(payload.get("weighted_score_5", 0.0) * 2, 2) if payload.get("weighted_score_5") is not None else None,
                "integrity_and_control_flags": pse.get("integrity_and_control_flags", []),
                "confidence": pse.get("confidence", "provisional"),
                "verified_strengths": pse.get("verified_strengths", []),
                "verified_defects": pse.get("verified_defects", []),
                "objective": payload.get("objective", [])
            }
            jsonschema.validate(instance=out_rec, schema=EVALUATION_SCHEMA)
            admitted_records.append(out_rec)

            rec_sha = compute_sha256(json.dumps(out_rec, sort_keys=True).encode("utf-8"))

            comment_bindings.append({
                "comment_id": cid,
                "author": author,
                "created_at": created_at,
                "updated_at": updated_at,
                "body_sha256": body_sha,
                "classification": "admitted",
                "evaluation_run_id": run_id,
                "canonical_record_sha256": rec_sha,
                "terminal_disposition": None,
                "pending_reason_code": None,
                "cleanup_eligible": True
            })

        elif disp == "pending_controller_action":
            stable_reason_code = "PENDING_CONTROLLER_ACTION"
            pending_items.append({
                "comment_id": cid,
                "reason": str(reason),
                "body_sha256": body_sha,
                "created_at": created_at,
                "updated_at": updated_at
            })
            comment_bindings.append({
                "comment_id": cid,
                "author": author,
                "created_at": created_at,
                "updated_at": updated_at,
                "body_sha256": body_sha,
                "classification": "pending",
                "evaluation_run_id": None,
                "canonical_record_sha256": None,
                "terminal_disposition": None,
                "pending_reason_code": stable_reason_code,
                "cleanup_eligible": False
            })

        else:
            # Terminal disposition (already_recorded, duplicate, owner_withdrawn, no_marker, invalid_json, prohibited_identity, ineligible)
            terminal_dispositions[str(cid)] = {
                "disposition": disp,
                "reason": str(reason),
                "comment_body_sha256": body_sha
            }
            disp_rec = {
                "schema_version": 1,
                "comment_id": cid,
                "disposition": disp,
                "reason": str(reason),
                "processed_at": created_at,
                "comment_body_sha256": body_sha
            }
            jsonschema.validate(instance=disp_rec, schema=DISPOSITION_SCHEMA)
            disposition_records.append(disp_rec)

            is_cleanup_eligible = disp in ["already_recorded", "duplicate", "owner_withdrawn"]
            if is_cleanup_eligible:
                cleanup_candidates.append(cid)

            comment_bindings.append({
                "comment_id": cid,
                "author": author,
                "created_at": created_at,
                "updated_at": updated_at,
                "body_sha256": body_sha,
                "classification": "terminal",
                "evaluation_run_id": payload.get("evaluation_run_id") if isinstance(payload, dict) else None,
                "canonical_record_sha256": None,
                "terminal_disposition": disp,
                "pending_reason_code": None,
                "cleanup_eligible": is_cleanup_eligible
            })

    # 2. Snapshot 2: Re-fetch queue comments and verify complete queue snapshot equality
    comments_snap2 = fetch_live_142_comments()
    issue_meta2 = fetch_issue_metadata()

    if len(comments_snap2) != len(comments_snap1):
        raise RuntimeError(f"Race condition detected: queue count changed from {len(comments_snap1)} to {len(comments_snap2)}")

    snap2_canon_str = json.dumps([{
        "id": c["id"],
        "user": c.get("user", {}).get("login"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "body_sha256": compute_sha256(c.get("body", "").encode("utf-8"))
    } for c in comments_snap2], sort_keys=True)
    snap2_hash = compute_sha256(snap2_canon_str.encode("utf-8"))

    if snap2_hash != snap1_hash:
        raise RuntimeError("Race condition detected: full queue snapshot SHA-256 mismatch!")

    # Complete final dataset
    final_ledger_records = preserved_base_records + admitted_records

    # Construct candidate serialized strings for staged hash validation
    evaluations_bytes = "".join(json.dumps(r) + "\n" for r in final_ledger_records).encode("utf-8")
    dispositions_bytes = "".join(json.dumps(d) + "\n" for d in disposition_records).encode("utf-8")

    evaluations_sha = compute_sha256(evaluations_bytes)
    dispositions_sha = compute_sha256(dispositions_bytes)

    # Staged rebuild of views
    # Build view strings in memory
    readme_sha = compute_sha256((ROOT / "README.md").read_bytes()) if (ROOT / "README.md").exists() else ""
    scorecard_sha = compute_sha256((ROOT / "scorecard.md").read_bytes()) if (ROOT / "scorecard.md").exists() else ""
    recommendation_sha = compute_sha256((ROOT / "analysis" / "model-recommendation.json").read_bytes()) if (ROOT / "analysis" / "model-recommendation.json").exists() else ""

    # Construct candidate batch receipt
    batch_receipt = {
        "schema_version": 1,
        "receipt_type": "batch",
        "batch_id": config.batch_id,
        "batch_mode": config.operating_mode,
        "controller_run_id": config.controller_authority,
        "controller_authority": config.controller_authority,
        "base_sha": config.base_sha,
        "pr_number": config.pr_number,
        "source_comment_watermark": max_comment_id,
        "full_queue_count": full_queue_count,
        "latest_observed_update_time": max_updated_at,
        "queue_snapshot_sha256": snap1_hash,
        "source_comment_ids": [c["id"] for c in comments_snap1],
        "source_body_sha256": {str(k): v for k, v in snap1_comment_hashes.items()},
        "admitted_run_ids": admitted_run_ids,
        "dispositions": terminal_dispositions,
        "pending_items": pending_items,
        "cleanup_candidates": cleanup_candidates,
        "comment_bindings": comment_bindings,
        "canonical_hashes": {
            "evaluations_jsonl": evaluations_sha,
            "readme_md": readme_sha,
            "scorecard_md": scorecard_sha,
            "model_recommendation_json": recommendation_sha,
            "dispositions_jsonl": dispositions_sha
        }
    }

    # Validate batch receipt against schema
    jsonschema.validate(instance=batch_receipt, schema=RECEIPT_SCHEMA)

    if config.dry_run:
        return {
            "status": "DRY_RUN_PASSED",
            "operating_mode": config.operating_mode,
            "full_queue_count": full_queue_count,
            "preserved_base_count": len(preserved_base_records),
            "admitted_count": len(admitted_records),
            "total_final_records": len(final_ledger_records),
            "disposition_count": len(disposition_records),
            "pending_count": len(pending_items),
            "watermark": max_comment_id,
            "latest_update_time": max_updated_at,
            "snapshot_hash": snap1_hash
        }

    # Atomic Tracked Mutations (only after all staged validations passed)
    # 1. Write evaluations.jsonl
    with open(LEDGER_PATH, "wb") as f:
        f.write(evaluations_bytes)

    # 2. Write ledger/dispositions.jsonl
    DISPOSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISPOSITIONS_PATH, "wb") as f:
        f.write(dispositions_bytes)

    # 3. Clean up invalid unmerged Amendment 003 receipt if in initial mode
    if config.operating_mode == "initial":
        old_amd3 = BATCH_RECEIPTS_DIR / "batch-20260729-gate3-amendment-003.json"
        if old_amd3.exists():
            try:
                old_amd3.unlink()
            except Exception:
                pass

    # 4. Write batch receipt
    with open(target_receipt_path, "w", encoding="utf-8") as f:
        json.dump(batch_receipt, f, indent=2)

    # 5. Rebuild views and update generated hashes in batch receipt
    rebuild_views(total_queued_count=len(pending_items))

    # Re-read final generated hashes and update receipt
    final_eval_sha = compute_sha256(LEDGER_PATH.read_bytes())
    final_readme_sha = compute_sha256((ROOT / "README.md").read_bytes())
    final_scorecard_sha = compute_sha256((ROOT / "scorecard.md").read_bytes())
    final_rec_sha = compute_sha256((ROOT / "analysis" / "model-recommendation.json").read_bytes())
    final_disp_sha = compute_sha256(DISPOSITIONS_PATH.read_bytes())

    batch_receipt["canonical_hashes"] = {
        "evaluations_jsonl": final_eval_sha,
        "readme_md": final_readme_sha,
        "scorecard_md": final_scorecard_sha,
        "model_recommendation_json": final_rec_sha,
        "dispositions_jsonl": final_disp_sha
    }
    with open(target_receipt_path, "w", encoding="utf-8") as f:
        json.dump(batch_receipt, f, indent=2)

    # Run public safety audit check
    safety_code = audit_public_safety_main()
    if safety_code != 0:
        raise RuntimeError("Public Safety audit failed after batch mutation!")

    return {
        "status": "SUCCESS",
        "operating_mode": config.operating_mode,
        "batch_id": config.batch_id,
        "full_queue_count": full_queue_count,
        "preserved_base_count": len(preserved_base_records),
        "admitted_count": len(admitted_records),
        "total_final_records": len(final_ledger_records),
        "disposition_count": len(disposition_records),
        "pending_count": len(pending_items),
        "watermark": max_comment_id,
        "latest_update_time": max_updated_at,
        "snapshot_hash": snap1_hash,
        "evaluations_sha256": final_eval_sha
    }

if __name__ == "__main__":
    cfg = ProcessBatchConfig()
    result = process_batch(cfg)
    print("Batch processing complete!")
    print(json.dumps(result, indent=2))
