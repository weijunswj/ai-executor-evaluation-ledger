from pathlib import PurePosixPath
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
        normalized = file_path.replace("\\", "/")
        relative = normalized.removeprefix(ALLOWED_CLEANUP_PREFIXES[0])
        is_cleanup_receipt = (
            normalized == file_path
            and normalized.startswith(ALLOWED_CLEANUP_PREFIXES[0])
            and relative.endswith(".json")
            and relative not in {"", ".", ".."}
            and PurePosixPath(relative).name == relative
            and ".." not in PurePosixPath(relative).parts
        )
        if not is_cleanup_receipt:
            return {
                "scope": "SEMANTIC_EVALUATION",
                "auto_merge_allowed": False,
                "reason": "non_receipt_path_requires_semantic_review"
            }

    return {
        "scope": "CLEANUP_ONLY",
        "auto_merge_allowed": True,
        "reason": "PR contains only standalone cleanup receipts under ledger/receipts/cleanup/"
    }
