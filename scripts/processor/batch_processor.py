import json
import hashlib
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.processor.intake_parser import parse_intake_comment, UUID_PATTERN

LEDGER_PATH = ROOT / "evaluations.jsonl"
DISPOSITIONS_PATH = ROOT / "ledger" / "dispositions.jsonl"
BATCH_RECEIPTS_DIR = ROOT / "ledger" / "receipts" / "batches"

def fetch_live_142_comments() -> List[Dict[str, Any]]:
    cmd = ["gh", "api", "repos/weijunswj/ai-executor-evaluation-ledger/issues/142/comments", "--paginate"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch #142 comments: {res.stderr}")
    return json.loads(res.stdout)

def process_batch() -> Dict[str, Any]:
    comments = fetch_live_142_comments()

    # Load recorded run IDs
    recorded_run_ids = set()
    if LEDGER_PATH.exists():
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
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
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        source_body_sha256[str(cid)] = body_sha

        disp, payload, reason = parse_intake_comment(cid, body, recorded_run_ids, seen_candidate_ids)

        if disp == "admitted":
            run_id = payload["evaluation_run_id"]
            seen_candidate_ids.add(run_id)
            admitted_run_ids.append(run_id)
            source_comment_ids.append(cid)
            cleanup_candidates.append(cid)

            # Map payload to schema v2 record
            evidence = payload.get("public_safe_evidence", {})
            eval_record = {
                "schema_version": 2,
                "record_type": "evaluation",
                "run_id": run_id,
                "reviewed_at": datetime.utcnow().isoformat() + "Z",
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
                "scores": payload.get("score_dimensions", {}),
                "weighted_score_5": payload.get("weighted_score_5", 0.0),
                "confidence": evidence.get("confidence", payload.get("confidence", "anecdotal")),
                "verified_strengths": evidence.get("verified_strengths", []),
                "verified_defects": evidence.get("verified_defects", []),
                "integrity_and_control_flags": evidence.get("integrity_and_control_flags", [])
            }
            admitted_records.append(eval_record)
        else:
            eval_id = payload.get("evaluation_run_id") if isinstance(payload, dict) else None
            if eval_id and UUID_PATTERN.search(str(eval_id)):
                eval_id = "[REDACTED_UUID]"

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
                "processed_at": datetime.utcnow().isoformat() + "Z"
            })

    # Append admitted records to evaluations.jsonl
    if admitted_records:
        with open(LEDGER_PATH, "a", encoding="utf-8", newline="\n") as f:
            for r in admitted_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Append disposition records to ledger/dispositions.jsonl
    DISPOSITIONS_PATH.parent.mkdir(exist_ok=True)
    if disposition_records:
        with open(DISPOSITIONS_PATH, "a", encoding="utf-8", newline="\n") as f:
            for r in disposition_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Generate batch receipt
    BATCH_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = f"batch-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Compute record hashes
    with open(LEDGER_PATH, "rb") as f:
        ledger_sha = hashlib.sha256(f.read()).hexdigest()

    batch_receipt = {
        "schema_version": 1,
        "receipt_type": "batch",
        "batch_id": batch_id,
        "source_comment_ids": source_comment_ids,
        "source_body_sha256": source_body_sha256,
        "admitted_run_ids": admitted_run_ids,
        "terminal_dispositions": terminal_dispositions,
        "canonical_record_hashes": {"evaluations_jsonl": ledger_sha},
        "analysis_manifest_hash": "sha256-computed",
        "generated_readme_hash": "sha256-computed",
        "generated_scorecard_hash": "sha256-computed",
        "pull_request_number": None,
        "base_sha": "27748b1fa4b70eb69f18047c31ec97c3505beb88",
        "exact_head_sha": "head_sha",
        "controller_authority": "2026-07-29-ledger-integrated-processor-gate3-001",
        "cleanup_candidates": cleanup_candidates
    }

    batch_file = BATCH_RECEIPTS_DIR / f"{batch_id}.json"
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(batch_receipt, f, indent=2)

    return {
        "batch_id": batch_id,
        "total_comments_inspected": len(comments),
        "admitted_count": len(admitted_records),
        "disposition_count": len(disposition_records),
        "batch_file": str(batch_file)
    }

if __name__ == "__main__":
    res = process_batch()
    print("Batch processing complete!")
    print(json.dumps(res, indent=2))
