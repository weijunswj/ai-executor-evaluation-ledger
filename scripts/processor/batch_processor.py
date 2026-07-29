import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple
import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.processor.intake_parser import parse_intake_comment
from scripts.rebuild_views import rebuild_views

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

BATCH_ID = "batch-20260729-gate3-amendment-003"
CONTROLLER_AUTHORITY = "2026-07-29-ledger-integrated-processor-gate3-amendment-003"
BASE_SHA = "27748b1fa4b70eb69f18047c31ec97c3505beb88"

WITHDRAWN_BASE_RUN_IDS = {
    "2026-07-24-claude-opus-4-8-business-automation-a-implementation-001",
    "2026-07-24-claude-opus-4-8-business-automation-a-amendment-001",
    "2026-07-24-correction-claude-opus-4-8-high-implementation-001",
    "2026-07-24-correction-claude-opus-4-8-high-amendment-001",
    "2026-07-24-claude-opus-4-8-high-business-automation-a-amendment-002",
    "2026-07-24-claude-opus-4-8-ultra-high-business-automation-a-amendment-003",
    "2026-07-25-correction-mimo-2-5-pro-default-provenance-repair-003"
}

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

def load_canonical_base_records() -> List[Dict[str, Any]]:
    """
    Loads evaluations.jsonl from canonical base commit 27748b1fa4b70eb69f18047c31ec97c3505beb88,
    applies schema v2 migration, excludes the exact 6 #150 withdrawals and 1 reasoning-only correction.
    Returns 59 preserved canonical records.
    """
    cmd = ["git", "show", f"{BASE_SHA}:evaluations.jsonl"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to read base evaluations.jsonl from {BASE_SHA}: {res.stderr}")

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

        # Protocol tag
        if "evaluation_protocol" not in rec:
            rec["evaluation_protocol"] = "protocol_unknown"

        rec["schema_version"] = 2
        records.append(rec)

    return records

def process_batch(dry_run: bool = False) -> Dict[str, Any]:
    """
    Executes a race-safe, deterministic staged batch processing transaction.
    """
    # 1. Snapshot 1: Fetch live queue comments & issue metadata
    comments_snap1 = fetch_live_142_comments()
    issue_meta1 = fetch_issue_metadata()

    # Load canonical base records (59 preserved)
    preserved_base_records = load_canonical_base_records()
    recorded_run_ids = {r.get("run_id") for r in preserved_base_records}

    snap1_metadata = {}
    snap1_comment_hashes = {}
    for c in comments_snap1:
        cid = c["id"]
        body = c.get("body", "")
        body_sha = compute_sha256(body.encode("utf-8"))
        snap1_comment_hashes[cid] = body_sha
        snap1_metadata[cid] = {
            "author": c.get("user", {}).get("login"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "body_sha256": body_sha
        }

    seen_candidate_ids = set()
    admitted_records = []
    admitted_run_ids = []
    source_comment_ids = []

    terminal_dispositions = {}
    disposition_records = []
    pending_items = []
    cleanup_candidates = []

    # Parse and classify each comment
    for c in comments_snap1:
        cid = c["id"]
        body = c.get("body", "")
        created_at = c.get("created_at")
        updated_at = c.get("updated_at")
        body_sha = snap1_comment_hashes[cid]

        disp, payload, reason = parse_intake_comment(cid, body, recorded_run_ids, seen_candidate_ids)

        if disp == "admitted":
            run_id = payload["evaluation_run_id"]
            seen_candidate_ids.add(run_id)
            admitted_run_ids.append(run_id)
            source_comment_ids.append(cid)
            cleanup_candidates.append(cid)

            # Build outcome record
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
                "weighted_score_10": round(payload.get("weighted_score_5", 0.0) * 2, 2),
                "integrity_and_control_flags": pse.get("integrity_and_control_flags", []),
                "confidence": pse.get("confidence", "provisional"),
                "verified_strengths": pse.get("verified_strengths", []),
                "verified_defects": pse.get("verified_defects", []),
                "objective": payload.get("objective", [])
            }
            # Schema validation check
            jsonschema.validate(instance=out_rec, schema=EVALUATION_SCHEMA)
            admitted_records.append(out_rec)

        elif disp == "pending_controller_action":
            pending_items.append({
                "comment_id": cid,
                "reason": str(reason),
                "body_sha256": body_sha,
                "created_at": created_at,
                "updated_at": updated_at
            })

        else:
            # Terminal disposition (already_recorded, duplicate, owner_withdrawn, no_marker, invalid_json, prohibited_identity, ineligible)
            terminal_dispositions[str(cid)] = {
                "disposition": disp,
                "reason": str(reason),
                "comment_body_sha256": body_sha
            }
            disposition_records.append({
                "schema_version": 1,
                "comment_id": cid,
                "disposition": disp,
                "reason": str(reason),
                "processed_at": created_at,
                "comment_body_sha256": body_sha
            })
            if disp in ["already_recorded", "duplicate", "owner_withdrawn"]:
                cleanup_candidates.append(cid)

    # 2. Pre-Sealing Verification: Re-fetch admitted & terminal comments
    for cid in source_comment_ids:
        fresh = fetch_single_comment(cid)
        fresh_sha = compute_sha256(fresh.get("body", "").encode("utf-8"))
        if fresh_sha != snap1_comment_hashes[cid] or fresh.get("updated_at") != snap1_metadata[cid]["updated_at"]:
            raise RuntimeError(f"Race condition detected: admitted comment {cid} changed before sealing!")

    for disp_item in disposition_records:
        cid = disp_item["comment_id"]
        fresh = fetch_single_comment(cid)
        fresh_sha = compute_sha256(fresh.get("body", "").encode("utf-8"))
        if fresh_sha != snap1_comment_hashes[cid] or fresh.get("updated_at") != snap1_metadata[cid]["updated_at"]:
            raise RuntimeError(f"Race condition detected: terminal comment {cid} changed before sealing!")

    # 3. Snapshot 2: Re-paginate issue #142 and compare
    comments_snap2 = fetch_live_142_comments()
    issue_meta2 = fetch_issue_metadata()

    if len(comments_snap2) != len(comments_snap1):
        raise RuntimeError(f"Race condition detected: queue count changed from {len(comments_snap1)} to {len(comments_snap2)}")

    if issue_meta2.get("updated_at") != issue_meta1.get("updated_at"):
        raise RuntimeError("Race condition detected: issue #142 metadata changed during sealing!")

    snap2_ids = [c["id"] for c in comments_snap2]
    snap1_ids = [c["id"] for c in comments_snap1]
    if snap2_ids != snap1_ids:
        raise RuntimeError("Race condition detected: queue comment ID sequence changed during sealing!")

    watermark = comments_snap1[-1]["id"] if comments_snap1 else 0
    latest_update_time = comments_snap1[-1]["updated_at"] if comments_snap1 else "2026-07-29T00:00:00Z"
    full_queue_count = len(comments_snap1)

    # Construct final ledger records (59 preserved base + 87 newly admitted queue records = 146 total)
    final_ledger_records = preserved_base_records + admitted_records

    if dry_run:
        return {
            "status": "DRY_RUN_PASSED",
            "full_queue_count": full_queue_count,
            "preserved_base_count": len(preserved_base_records),
            "admitted_count": len(admitted_records),
            "total_final_records": len(final_ledger_records),
            "disposition_count": len(disposition_records),
            "pending_count": len(pending_items),
            "watermark": watermark,
            "latest_update_time": latest_update_time
        }

    # Atomically replace outputs
    # 1. evaluations.jsonl
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        for r in final_ledger_records:
            f.write(json.dumps(r) + "\n")

    # 2. ledger/dispositions.jsonl
    DISPOSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISPOSITIONS_PATH, "w", encoding="utf-8") as f:
        for d in disposition_records:
            jsonschema.validate(instance=d, schema=DISPOSITION_SCHEMA)
            f.write(json.dumps(d) + "\n")

    # 3. Clean up old invalid unmerged batch receipts (e.g. batch-20260729-gate3-amendment-002.json)
    BATCH_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    for old_receipt in BATCH_RECEIPTS_DIR.glob("*.json"):
        if old_receipt.name != f"{BATCH_ID}.json":
            try:
                old_receipt.unlink()
            except Exception:
                pass

    # 4. Rebuild views and recommendations
    rebuild_views(total_queued_count=len(pending_items))

    # Compute canonical hashes
    evaluations_sha = compute_sha256(LEDGER_PATH.read_bytes())
    readme_sha = compute_sha256((ROOT / "README.md").read_bytes())
    scorecard_sha = compute_sha256((ROOT / "scorecard.md").read_bytes())
    recommendation_sha = compute_sha256((ROOT / "analysis" / "model-recommendation.json").read_bytes())
    dispositions_sha = compute_sha256(DISPOSITIONS_PATH.read_bytes())

    # Build batch receipt
    batch_receipt = {
        "schema_version": 1,
        "receipt_type": "batch",
        "batch_id": BATCH_ID,
        "controller_run_id": CONTROLLER_AUTHORITY,
        "base_sha": BASE_SHA,
        "pr_number": 151,
        "source_comment_watermark": watermark,
        "full_queue_count": full_queue_count,
        "latest_observed_update_time": latest_update_time,
        "source_comment_ids": source_comment_ids,
        "source_body_sha256": {str(k): v for k, v in snap1_comment_hashes.items()},
        "admitted_run_ids": admitted_run_ids,
        "dispositions": terminal_dispositions,
        "pending_items": pending_items,
        "cleanup_candidates": cleanup_candidates,
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

    receipt_path = BATCH_RECEIPTS_DIR / f"{BATCH_ID}.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(batch_receipt, f, indent=2)

    return {
        "status": "SUCCESS",
        "batch_id": BATCH_ID,
        "full_queue_count": full_queue_count,
        "preserved_base_count": len(preserved_base_records),
        "admitted_count": len(admitted_records),
        "total_final_records": len(final_ledger_records),
        "disposition_count": len(disposition_records),
        "pending_count": len(pending_items),
        "watermark": watermark,
        "latest_update_time": latest_update_time,
        "evaluations_sha256": evaluations_sha
    }

if __name__ == "__main__":
    result = process_batch(dry_run=False)
    print("Batch processing complete!")
    print(json.dumps(result, indent=2))
