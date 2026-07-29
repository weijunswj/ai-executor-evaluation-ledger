import argparse
import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple

ROOT = Path(__file__).resolve().parents[2]

def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def fetch_live_comment(comment_id: int) -> Dict[str, Any]:
    cmd = ["gh", "api", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch comment {comment_id}: {res.stderr}")
    return json.loads(res.stdout)

def delete_live_comment(comment_id: int) -> bool:
    cmd = ["gh", "api", "-X", "DELETE", f"repos/weijunswj/ai-executor-evaluation-ledger/issues/comments/{comment_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0

def run_cleanup(dry_run: bool = False, canonical_merge_sha: str = None) -> Dict[str, Any]:
    """
    Executes post-merge cleanup logic.
    --dry-run fetches real comment, verifies ID & body hash, reports proposed action without deleting.
    """
    batches_dir = ROOT / "ledger" / "receipts" / "batches"
    if not batches_dir.exists():
        return {"status": "NO_BATCHES", "deleted_count": 0, "dry_run": dry_run}

    batch_files = list(batches_dir.glob("*.json"))
    if not batch_files:
        return {"status": "NO_BATCHES", "deleted_count": 0, "dry_run": dry_run}

    merge_sha = canonical_merge_sha or os.environ.get("GITHUB_SHA", "27748b1fa4b70eb69f18047c31ec97c3505beb88")
    evaluations_sha = compute_sha256((ROOT / "evaluations.jsonl").read_bytes()) if (ROOT / "evaluations.jsonl").exists() else "0" * 64

    deleted_count = 0
    cleanup_receipts = []

    for bfile in batch_files:
        try:
            batch_data = json.loads(bfile.read_text(encoding="utf-8"))
        except Exception:
            continue

        batch_id = batch_data.get("batch_id")
        candidates = batch_data.get("cleanup_candidates", [])
        body_hashes = batch_data.get("source_body_sha256", {})

        deleted_ids = []
        deleted_hashes = {}
        retained_ids = []
        retained_reasons = {}

        for cid in candidates:
            str_cid = str(cid)
            expected_hash = body_hashes.get(str_cid)

            if not expected_hash:
                retained_ids.append(cid)
                retained_reasons[str_cid] = "Missing expected body SHA-256 hash binding"
                continue

            try:
                comment_data = fetch_live_comment(cid)
                actual_body = comment_data.get("body", "")
                actual_hash = compute_sha256(actual_body.encode("utf-8"))

                if actual_hash != expected_hash:
                    retained_ids.append(cid)
                    retained_reasons[str_cid] = "Body SHA-256 hash mismatch (comment modified)"
                    continue

                if dry_run:
                    # Dry-run: report proposed deletion without executing DELETE
                    deleted_ids.append(cid)
                    deleted_hashes[str_cid] = expected_hash
                else:
                    # Live mode: execute API DELETE and verify deletion
                    success = delete_live_comment(cid)
                    if success:
                        deleted_ids.append(cid)
                        deleted_hashes[str_cid] = expected_hash
                    else:
                        retained_ids.append(cid)
                        retained_reasons[str_cid] = "GitHub API DELETE request failed"
            except Exception as exc:
                retained_ids.append(cid)
                retained_reasons[str_cid] = f"Fetch failure: {str(exc)}"

        cleanup_receipt = {
            "schema_version": 1,
            "receipt_type": "cleanup",
            "batch_id": batch_id,
            "canonical_merge_sha": merge_sha,
            "canonical_evaluations_blob_sha": evaluations_sha,
            "deleted_comment_ids": deleted_ids,
            "deleted_comment_hashes": deleted_hashes,
            "retained_comment_ids": retained_ids,
            "retained_comment_reasons": retained_reasons,
            "cleanup_workflow_identity": "post-merge-cleanup-v1",
            "exact_result": "DRY_RUN_PASSED" if dry_run else ("SUCCESS" if not retained_ids else "PARTIAL_SUCCESS")
        }

        cleanup_receipts.append(cleanup_receipt)
        deleted_count += len(deleted_ids)

    return {
        "status": "DRY_RUN_PASSED" if dry_run else "COMPLETED",
        "deleted_count": deleted_count,
        "cleanup_receipts": cleanup_receipts,
        "dry_run": dry_run
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without deleting comments or writing PRs")
    args = parser.parse_args()

    result = run_cleanup(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
