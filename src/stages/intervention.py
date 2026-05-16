"""Stage 6: Targeted intervention design (segment-level).

The triggering logic is deterministic: scan the account reviews for a
segment showing declining outcomes (e.g. 3+ accounts in the same
segment flagged as declining). If found, design a corrective action.
Opus (high tier) because this is the highest-stakes synthesis stage
and runs at low frequency (bi-weekly).
"""
import json
from collections import defaultdict

from src.claude_client import ClaudeClient
from src.data_loader import CSData


def detect_segment_issue(account_reviews: list[dict], data: CSData) -> dict | None:
    """Deterministic segment-issue detection.

    Returns the segment + affected account_ids if a pattern is found,
    or None if no intervention needed this cycle.
    """
    by_segment: dict[str, list[str]] = defaultdict(list)
    for r in account_reviews:
        if r.get("_parse_error"):
            continue
        if r.get("health_delta") == "declining" and r.get("attention_needed"):
            aid = r.get("account_id")
            if not aid:
                continue
            acc_row = data.accounts[data.accounts.account_id == aid]
            if acc_row.empty:
                continue
            seg = acc_row.iloc[0].segment
            by_segment[seg].append(aid)

    for seg, aids in by_segment.items():
        if len(aids) >= 2:  # threshold tuned for the 18-account sample
            return {"segment": seg, "account_ids": aids}
    return None


def run(client: ClaudeClient, data: CSData, account_reviews: list[dict]) -> dict | None:
    issue = detect_segment_issue(account_reviews, data)
    if not issue:
        return {"segment_issue_detected": False, "note": "No segment-level pattern this cycle."}

    # Build the segment context
    contexts = []
    for aid in issue["account_ids"]:
        contexts.append(data.account_context(aid, include_call_notes=False, include_usage=True))
    user_content = (
        f"SEGMENT: {issue['segment']}\n"
        f"AFFECTED ACCOUNTS: {', '.join(issue['account_ids'])}\n\n"
        + "\n\n---\n\n".join(contexts)
    )
    plan = client.call(
        stage="intervention_design",
        tier="high",
        system_prompt_name="intervention_design",
        user_content=user_content,
        max_tokens=1000,
    )
    return {"segment_issue_detected": True, "trigger": issue, "plan": plan}
