import json
import re
from typing import Dict, Any, Optional, Tuple

OWNERSHIP_MARKER = "<!-- ledger-source-watch:v1 -->"

def parse_pr_body(body: str) -> Tuple[Dict[str, Any], str]:
    """
    Parses a PR body containing a byte-zero Source Watch metadata envelope.
    Requires body to start at byte zero with <!-- ledger-source-watch:v1 -->,
    followed by exactly one triple-backtick fenced JSON metadata block.
    Returns (metadata_dict, remaining_human_readable_body).
    Fails closed on missing marker, missing/malformed fence, non-dict metadata,
    duplicate markers/fences, or candidate metadata JSON in trailing text.
    """
    if not body.startswith(OWNERSHIP_MARKER):
        raise ValueError("PR body does not start at byte zero with exact ownership marker")

    rest = body[len(OWNERSHIP_MARKER):]
    rest_lstripped = rest.lstrip("\r\n")

    if not (rest_lstripped.startswith("```json") or rest_lstripped.startswith("```")):
        raise ValueError("PR body metadata block does not start with triple backticks fence")

    fence_end_idx = rest_lstripped.find("```", 3)
    if fence_end_idx == -1:
        raise ValueError("PR body metadata block missing closing fence")

    if rest_lstripped.startswith("```json"):
        json_str = rest_lstripped[7:fence_end_idx].strip()
    else:
        json_str = rest_lstripped[3:fence_end_idx].strip()

    try:
        metadata = json.loads(json_str)
    except Exception as e:
        raise ValueError(f"Malformed metadata JSON in PR body: {str(e)}")

    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a single JSON object")

    remaining_body = rest_lstripped[fence_end_idx + 3:].lstrip("\r\n")

    # Fail closed checks on trailing body
    if OWNERSHIP_MARKER in remaining_body:
        raise ValueError("Ambiguous PR body: contains additional ownership marker in trailing text")

    if "source_watch_pr_metadata" in remaining_body or '"record_type": "source_watch_pr_metadata"' in remaining_body:
        raise ValueError("Ambiguous PR body: contains another candidate metadata block in trailing text")

    return metadata, remaining_body

class SourceWatchPlanner:
    """
    Deterministic planner, classifier, and validator for Source-Watch owned PR lane.
    Operates without external network calls or credentials.
    """
    OWNERSHIP_MARKER = OWNERSHIP_MARKER

    def plan_pr_action(self,
                       pr_meta: Optional[Dict[str, Any]],
                       has_pending_work: bool,
                       current_head_sha: str) -> Dict[str, Any]:
        """
        Determines the exact PR action given current PR metadata and pending work state.
        """
        if not has_pending_work:
            return {
                "action": "NO_WORK",
                "reason": "No pending work to process"
            }

        if pr_meta is None:
            return {
                "action": "CREATE_NEW_DRAFT_PR",
                "reason": "No active Source Watch PR exists; create new draft PR"
            }

        body = pr_meta.get("body", "")
        try:
            parsed_meta, remaining = parse_pr_body(body)
        except Exception as err:
            return {
                "action": "REFUSE_AMBIGUOUS_OWNERSHIP",
                "reason": f"PR body metadata envelope invalid: {str(err)}"
            }

        # Check draft state
        if not pr_meta.get("is_draft", False):
            return {
                "action": "REFUSE_NOT_DRAFT",
                "reason": "Target PR is not in draft state"
            }

        # Check review freeze / review started
        if pr_meta.get("is_frozen", False) or parsed_meta.get("frozen", False):
            return {
                "action": "REFUSE_FROZEN",
                "reason": "PR is under review freeze or review has begun"
            }

        # Check expected head SHA match
        expected_head = parsed_meta.get("final_expected_head") or parsed_meta.get("expected_head_sha")
        if expected_head and expected_head != current_head_sha:
            return {
                "action": "REFUSE_UNEXPECTED_HEAD",
                "reason": f"Expected head SHA ({expected_head}) does not match current head SHA ({current_head_sha})"
            }

        return {
            "action": "UPDATE_EXISTING_PR",
            "pr_number": pr_meta.get("number"),
            "reason": "Safe mutable Source Watch PR available for append"
        }
