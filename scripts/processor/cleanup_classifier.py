from typing import List, Dict, Any

ALLOWED_CLEANUP_PATHS_PREFIXES = (
    "ledger/receipts/cleanup/",
)

ALLOWED_GENERATED_FILES = {
    "README.md",
    "scorecard.md",
    "analysis/model-recommendation.json"
}

def classify_pr_scope(changed_files: List[str]) -> Dict[str, Any]:
    """
    Classifies PR scope to determine if automatic merge is permitted.
    Cleanup-only PRs may auto-merge under strict conditions.
    Semantic PRs require fresh controller exact-head approval.
    """
    if not changed_files:
        return {"scope": "SEMANTIC_EVALUATION", "auto_merge_allowed": False, "reason": "No changed files"}

    for f in changed_files:
        is_cleanup_receipt = any(f.startswith(prefix) for prefix in ALLOWED_CLEANUP_PATHS_PREFIXES)
        is_generated_file = f in ALLOWED_GENERATED_FILES

        if not (is_cleanup_receipt or is_generated_file):
            return {
                "scope": "SEMANTIC_EVALUATION",
                "auto_merge_allowed": False,
                "reason": f"File '{f}' is not an authorized cleanup-receipt or generated file"
            }

    return {
        "scope": "CLEANUP_ONLY",
        "auto_merge_allowed": True,
        "reason": "PR contains only authorized cleanup receipts and byte-deterministic generated files"
    }
