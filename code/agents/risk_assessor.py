"""
Risk Assessor Agent: rule-based risk flag generation from user_history.csv.
No LLM calls — pure logic.
User history NEVER changes claim_status, only adds to risk_flags.
"""
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def assess_risk(user_history: dict[str, Any] | None) -> set[str]:
    """
    Assess user risk based on their claim history.

    Rules:
    - rejected_claim >= 2 → user_history_risk
    - manual_review_claim >= 1 → manual_review_required
    - history_flags contains non-"none" value → user_history_risk
    - last_90_days_claim_count >= 3 → user_history_risk

    Args:
        user_history: dict from user_history.csv for this user_id, or None

    Returns:
        Set of risk flag strings to merge with vision flags.
    """
    if user_history is None:
        return set()

    flags = set()

    # Rule 1: rejected_claim >= 2
    if user_history.get("rejected_claim", 0) >= 2:
        flags.add("user_history_risk")

    # Rule 2: manual_review_claim >= 1
    if user_history.get("manual_review_claim", 0) >= 1:
        flags.add("manual_review_required")

    # Rule 3: history_flags is non-empty and non-"none"
    history_flags = user_history.get("history_flags", "none").strip()
    if history_flags and history_flags.lower() != "none":
        flags.add("user_history_risk")
        # Also propagate individual flags from history
        for hf in history_flags.split(";"):
            hf = hf.strip()
            if hf and hf != "none":
                flags.add(hf)

    # Rule 4: last_90_days_claim_count >= 3
    if user_history.get("last_90_days_claim_count", 0) >= 3:
        flags.add("user_history_risk")

    return flags
