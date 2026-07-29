import argparse
import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RECEIPT_SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
with open(RECEIPT_SCHEMA_PATH, "r", encoding="utf-8") as f:
    RECEIPT_SCHEMA = json.load(f)

def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def fetch_live_comment(comment_id: int) -> Dict[str, Any]:
    cmd = ["gh", "api", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch comment {comment_id}: {res.stderr}")
    return json.loads(res.stdout)

def verify_comment_absent(comment_id: int) -> bool:
    cmd = ["gh", "api", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 and ("404" in res.stderr or "Not Found" in res.stderr):
        return True
    return False

def delete_live_comment(comment_id: int) -> bool:
    cmd = ["gh", "api", "-X", "DELETE", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0

def run_cleanup(dry_run: bool = False, canonical_merge_sha: str = None) -> Dict[str, Any]:
    """
    Executes post-merge cleanup logic with strict pre-deletion verification,
    activation switch check (LEDGER_CLEANUP_ENABLED=true), live deletion absence check (HTTP 404),
    and cleanup receipt publication planning.
    """
    batches_dir = ROOT / "ledger" / "receipts" / "batches"
    if not batches_dir.exists():
        return {"status": "NO_BATCHES", "deleted_count": 0, "dry_run": dry_run}

    batch_files = list(batches_dir.glob("*.json"))
    if not batch_files:
        return {"status": "NO_BATCHES", "deleted_count": 0, "dry_run": dry_run}

    merge_sha = canonical_merge_sha or os.environ.get("GITHUB_SHA", "27748b1fa4b70eb69f18047c31ec97c3505beb88")
    evaluations_sha = compute_sha256((ROOT / "evaluations.jsonl").read_bytes()) if (ROOT / "evaluations.jsonl").exists() else "0" * 64

    # Check activation switch
    cleanup_enabled_env = os.environ.get("LEDGER_CLEANUP_ENABLED", "").strip().lower()
    live_cleanup_active = (cleanup_enabled_env == "true") and not dry_run

    deleted_count = 0
    cleanup_receipts = []

    for bfile in batch_files:
        try:
            batch_data = json.loads(bfile.read_text(encoding="utf-8"))
            jsonschema.validate(instance=batch_data, schema=RECEIPT_SCHEMA)
        except Exception as exc:
            continue

        batch_id = batch_data.get("batch_id")
        candidates = batch_data.get("cleanup_candidates", [])
        body_hashes = batch_data.get("source_body_sha256", {})

        # Verify canonical hashes match batch receipt
        receipt_hashes = batch_data.get("canonical_hashes", {})
        if receipt_hashes.get("evaluations_jsonl") and receipt_hashes.get("evaluations_jsonl") != evaluations_sha:
            # Canonical evaluations hash mismatch -> skip deletion for safety
            cleanup_receipts.append({
                "schema_version": 1,
                "receipt_type": "cleanup",
                "batch_id": batch_id,
                "canonical_merge_sha": merge_sha,
                "canonical_evaluations_blob_sha": evaluations_sha,
                "deleted_comment_ids": [],
                "deleted_comment_hashes": {},
                "retained_comment_ids": candidates,
                "retained_comment_reasons": {str(cid): "Canonical evaluations hash mismatch" for cid in candidates},
                "cleanup_workflow_identity": "post-merge-cleanup-v1",
                "exact_result": "CANONICAL_HASH_MISMATCH"
            })
            continue

        verified_candidates = []
        deleted_ids = []
        deleted_hashes = {}
        retained_ids = []
        retained_reasons = {}

        for cid in candidates:
            str_cid = str(cid)
            expected_hash = body_hashes.get(str_cid)

            if not expected_hash:
                retained_ids.append(cid)
                retained_reasons[str_cid] = "MISSING_BODY_HASH_BINDING"
                continue

            try:
                comment_data = fetch_live_comment(cid)
                actual_body = comment_data.get("body", "")
                actual_hash = compute_sha256(actual_body.encode("utf-8"))

                if actual_hash != expected_hash:
                    retained_ids.append(cid)
                    retained_reasons[str_cid] = "BODY_HASH_MISMATCH"
                    continue

                if dry_run or not live_cleanup_active:
                    # Dry-run or inactive switch: report verified candidate without executing DELETE
                    verified_candidates.append(cid)
                else:
                    # Live mode with LEDGER_CLEANUP_ENABLED=true: execute API DELETE and verify absence via HTTP 404
                    success = delete_live_comment(cid)
                    if success:
                        # Re-fetch comment and verify HTTP 404 / absence
                        absent = verify_comment_absent(cid)
                        if absent:
                            deleted_ids.append(cid)
                            deleted_hashes[str_cid] = expected_hash
                        else:
                            retained_ids.append(cid)
                            retained_reasons[str_cid] = "ABSENCE_VERIFICATION_FAILED"
                    else:
                        retained_ids.append(cid)
                        retained_reasons[str_cid] = "GITHUB_API_DELETE_FAILED"
            except Exception as exc:
                retained_ids.append(cid)
                retained_reasons[str_cid] = f"FETCH_FAILURE: {str(exc)}"

        exact_result = "DRY_RUN_VERIFIED" if (dry_run or not live_cleanup_active) else ("SUCCESS" if not retained_ids else "PARTIAL_SUCCESS")

        cleanup_receipt = {
            "schema_version": 1,
            "receipt_type": "cleanup",
            "batch_id": batch_id,
            "canonical_merge_sha": merge_sha,
            "canonical_evaluations_blob_sha": evaluations_sha,
            "deleted_comment_ids": deleted_ids,
            "deleted_comment_hashes": deleted_hashes,
            "verified_deletion_candidates": verified_candidates,
            "retained_comment_ids": retained_ids,
            "retained_comment_reasons": retained_reasons,
            "cleanup_workflow_identity": "post-merge-cleanup-v1",
            "exact_result": exact_result,
            "cleanup_publication_status": "PENDING_OPERATOR_PUBLICATION",
            "publication_plan": {
                "status": "PENDING_OPERATOR_PUBLICATION",
                "target_branch": f"ledger/cleanup-batch-{batch_id}",
                "receipt_relative_path": f"ledger/receipts/cleanup/{batch_id}.json",
                "action": "create_or_update_draft_cleanup_pr"
            }
        }

        # Validate cleanup receipt
        jsonschema.validate(instance=cleanup_receipt, schema=RECEIPT_SCHEMA)
        cleanup_receipts.append(cleanup_receipt)
        deleted_count += len(deleted_ids)

    return {
        "status": "DRY_RUN_PASSED" if (dry_run or not live_cleanup_active) else "COMPLETED",
        "deleted_count": deleted_count,
        "cleanup_receipts": cleanup_receipts,
        "dry_run": dry_run,
        "live_cleanup_active": live_cleanup_active
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without deleting comments or writing PRs")
    args = parser.parse_args()

    result = run_cleanup(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
