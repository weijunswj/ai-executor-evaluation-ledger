from typing import List, Dict, Any

ALLOWED_CLEANUP_PREFIXES = (
    "ledger/receipts/cleanup/",
)

def classify_pr_scope(changed_files: List[str]) -> Dict[str, Any]:
    """
    Classifies PR scope to determine if automatic merge is permitted.
    Standalone cleanup-only PRs may contain ONLY ledger/receipts/cleanup/*.json.
    Any changes to README.md, scorecard.md, analysis/model-recommendation.json,
    evaluations.jsonl, schemas, workflows, or scripts make the PR scope SEMANTIC_EVALUATION.
    """
    if not changed_files:
        return {
            "scope": "SEMANTIC_EVALUATION",
            "auto_merge_allowed": False,
            "reason": "No changed files provided"
        }

    for file_path in changed_files:
        is_cleanup_receipt = any(file_path.startswith(prefix) for prefix in ALLOWED_CLEANUP_PREFIXES)
        if not is_cleanup_receipt:
            return {
                "scope": "SEMANTIC_EVALUATION",
                "auto_merge_allowed": False,
                "reason": f"File '{file_path}' is not a standalone cleanup receipt. Changed generated or code files require semantic review."
            }

    return {
        "scope": "CLEANUP_ONLY",
        "auto_merge_allowed": True,
        "reason": "PR contains only standalone cleanup receipts under ledger/receipts/cleanup/"
    }
