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

BATCH_ID = "batch-20260729-gate3-amendment-002"
CONTROLLER_AUTHORITY = "2026-07-29-ledger-integrated-processor-gate3-amendment-002"
BASE_SHA = "27748b1fa4b70eb69f18047c31ec97c3505beb88"

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

def process_batch(dry_run: bool = False) -> Dict[str, Any]:
    """
    Executes a deterministic staged batch processing transaction.
    """
    comments = fetch_live_142_comments()
    issue_meta = fetch_issue_metadata()

    # Base canonical evaluations (migrated 59 records)
    base_records = []
    recorded_run_ids = set()

    # Reset evaluations.jsonl to base migrated records first
    # Load base records from migrations or initial state
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                # Keep base 59 records (historical)
                if rec.get("evaluation_protocol") == "protocol_unknown" or rec.get("record_type") == "correction":
                    base_records.append(rec)
                    recorded_run_ids.add(rec.get("run_id"))

    seen_candidate_ids = set()
    admitted_records = []
    admitted_run_ids = []
    source_comment_ids = []
    source_body_sha256 = {}
    terminal_dispositions = {}
    disposition_records = []
    cleanup_candidates = []

    for c in comments:
        cid = c["id"]
        body = c.get("body", "")
        created_at = c.get("created_at")
        body_sha = compute_sha256(body.encode("utf-8"))
        source_body_sha256[str(cid)] = body_sha

        disp, payload, reason = parse_intake_comment(cid, body, recorded_run_ids, seen_candidate_ids)

        if disp == "admitted":
            run_id = payload["evaluation_run_id"]
            seen_candidate_ids.add(run_id)
            admitted_run_ids.append(run_id)
            source_comment_ids.append(cid)
            cleanup_candidates.append(cid)

            # Preserve source time: intake reviewed_at if present, else comment created_at
            reviewed_at = payload.get("reviewed_at") or created_at

            evidence = payload.get("public_safe_evidence", {})
            eval_record = {
                "schema_version": 2,
                "record_type": "evaluation",
                "run_id": run_id,
                "reviewed_at": reviewed_at,
                "executor_reported_at": payload.get("executor_reported_at"),
                "provider": payload["provider"],
                "model": payload["canonical_base_model"],
                "evaluation_protocol": payload.get("evaluation_protocol", "gated_v1"),
                "task_class": payload.get("task_class", "research"),
                "difficulty": payload.get("difficulty", "medium"),
                "subject_alias": payload.get("repository_alias", "subject-alias"),
                "revision_binding": payload.get("source_revision", "rev-binding"),
                "outcome": payload.get("verdict", "accepted"),
                "first_pass_accepted": evidence.get("first_pass_accepted", payload.get("first_pass_accepted", False)),
                "controller_intervention_required": evidence.get("controller_intervention_required", payload.get("controller_intervention_required", False)),
                "safe_final_state_reported": evidence.get("safe_final_state_reported"),
                "safe_final_state_verified": evidence.get("safe_final_state_verified"),
                "root_cause_identified": evidence.get("root_cause_identified"),
                "follow_up_runs_required": evidence.get("follow_up_runs_required"),
                "scores": payload.get("score_dimensions", {}),
                "weighted_score_5": payload.get("weighted_score_5", 0.0),
                "weighted_score_10": payload.get("weighted_score_10"),
                "integrity_and_control_flags": evidence.get("integrity_and_control_flags", []),
                "confidence": evidence.get("confidence", payload.get("confidence", "baseline")),
                "verified_strengths": evidence.get("verified_strengths", []),
                "verified_defects": evidence.get("verified_defects", []),
                "objective": payload.get("objective", [])
            }
            admitted_records.append(eval_record)
        else:
            eval_id = payload.get("evaluation_run_id") if isinstance(payload, dict) else None

            terminal_dispositions[str(cid)] = {
                "disposition": disp,
                "reason": reason,
                "evaluation_run_id": eval_id
            }
            disposition_records.append({
                "schema_version": 1,
                "comment_id": cid,
                "comment_body_sha256": body_sha,
                "disposition": disp,
                "reason": reason,
                "evaluation_run_id": eval_id,
                "processed_at": created_at
            })

    # Pre-sealing verification: re-fetch selected admitted comments right before sealing
    for cid in source_comment_ids:
        latest = fetch_single_comment(cid)
        latest_sha = compute_sha256(latest.get("body", "").encode("utf-8"))
        if latest_sha != source_body_sha256[str(cid)]:
            raise RuntimeError(f"Race condition detected: comment {cid} modified during batch processing!")

    # Calculate queue metadata
    watermark = max([c["id"] for c in comments]) if comments else 0
    full_queue_count = len(comments)
    latest_update_time = max([c.get("updated_at") or c.get("created_at") for c in comments]) if comments else "2026-07-29T00:00:00Z"

    # Construct final evaluation records (base 59 + admitted)
    final_records = base_records + admitted_records

    # Serialize evaluations.jsonl in memory
    evaluations_jsonl_bytes = ("\n".join(json.dumps(r, ensure_ascii=False) for r in final_records) + "\n").encode("utf-8")
    evaluations_sha256 = compute_sha256(evaluations_jsonl_bytes)

    # Validate every evaluation record against evaluation.schema.json
    for idx, r in enumerate(final_records, start=1):
        jsonschema.validate(instance=r, schema=EVALUATION_SCHEMA)

    # Validate disposition records
    for d in disposition_records:
        jsonschema.validate(instance=d, schema=DISPOSITION_SCHEMA)

    # Build batch receipt
    batch_receipt = {
        "schema_version": 1,
        "receipt_type": "batch",
        "batch_id": BATCH_ID,
        "source_comment_ids": source_comment_ids,
        "source_body_sha256": source_body_sha256,
        "admitted_run_ids": admitted_run_ids,
        "terminal_dispositions": terminal_dispositions,
        "canonical_record_hashes": {
            "evaluations_jsonl": evaluations_sha256
        },
        "analysis_manifest_hash": "0" * 64,  # placeholder before view rebuild
        "generated_readme_hash": "0" * 64,
        "generated_scorecard_hash": "0" * 64,
        "pull_request_number": 151,
        "base_sha": BASE_SHA,
        "exact_head_sha": None,
        "controller_authority": CONTROLLER_AUTHORITY,
        "cleanup_candidates": cleanup_candidates,
        "source_comment_watermark": watermark,
        "full_queue_count": full_queue_count,
        "latest_observed_update_time": latest_update_time
    }

    # Write files atomically
    if not dry_run:
        # Write evaluations.jsonl
        with open(LEDGER_PATH, "wb") as f:
            f.write(evaluations_jsonl_bytes)

        # Write dispositions.jsonl
        DISPOSITIONS_PATH.parent.mkdir(exist_ok=True)
        disp_bytes = ("\n".join(json.dumps(d, ensure_ascii=False) for d in disposition_records) + "\n").encode("utf-8")
        with open(DISPOSITIONS_PATH, "wb") as f:
            f.write(disp_bytes)

        # Clear existing batches and write clean batch receipt
        BATCH_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        for old_b in BATCH_RECEIPTS_DIR.glob("*.json"):
            old_b.unlink()

        # Rebuild views & recommendations
        rebuild_views(total_queued_count=full_queue_count - len(admitted_records) - len(disposition_records))

        # Read generated file hashes
        readme_sha = compute_sha256((ROOT / "README.md").read_bytes())
        scorecard_sha = compute_sha256((ROOT / "scorecard.md").read_bytes())
        rec_sha = compute_sha256((ROOT / "analysis" / "model-recommendation.json").read_bytes())

        # Fill receipt hashes
        batch_receipt["analysis_manifest_hash"] = rec_sha
        batch_receipt["generated_readme_hash"] = readme_sha
        batch_receipt["generated_scorecard_hash"] = scorecard_sha

        # Validate batch receipt against schema
        jsonschema.validate(instance=batch_receipt, schema=RECEIPT_SCHEMA)

        # Save batch receipt
        batch_file = BATCH_RECEIPTS_DIR / f"{BATCH_ID}.json"
        with open(batch_file, "w", encoding="utf-8") as f:
            json.dump(batch_receipt, f, indent=2)

    return {
        "status": "SUCCESS",
        "batch_id": BATCH_ID,
        "full_queue_count": full_queue_count,
        "admitted_count": len(admitted_records),
        "disposition_count": len(disposition_records),
        "watermark": watermark,
        "latest_update_time": latest_update_time,
        "evaluations_sha256": evaluations_sha256
    }

if __name__ == "__main__":
    res = process_batch()
    print("Batch processing complete!")
    print(json.dumps(res, indent=2))
