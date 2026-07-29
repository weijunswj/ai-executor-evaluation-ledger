import json
from typing import Dict, Any, Optional

class SourceWatchPlanner:
    """
    Deterministic planner, classifier, and validator for Source-Watch owned PR lane.
    Operates without external network calls or credentials.
    """
    OWNERSHIP_MARKER = "<!-- ledger-source-watch:v1 -->"

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

        # Check ownership marker
        body = pr_meta.get("body", "")
        if not body.startswith(self.OWNERSHIP_MARKER):
            return {
                "action": "REFUSE_AMBIGUOUS_OWNERSHIP",
                "reason": "PR body does not begin with exact ownership marker"
            }

        # Check draft state
        if not pr_meta.get("is_draft", False):
            return {
                "action": "REFUSE_NOT_DRAFT",
                "reason": "Target PR is not in draft state"
            }

        # Check mutable state in metadata
        parsed_meta = pr_meta.get("metadata", {})
        if not parsed_meta.get("mutable_state", False):
            return {
                "action": "REFUSE_IMMUTABLE",
                "reason": "PR metadata indicates mutable_state is false"
            }

        # Check review freeze / review started
        if pr_meta.get("is_frozen", False) or parsed_meta.get("review_freeze_state", False):
            return {
                "action": "REFUSE_FROZEN",
                "reason": "PR is under review freeze or review has begun"
            }

        # Check expected head SHA match
        expected_head = parsed_meta.get("expected_head_sha")
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
