"""Stage 2: Portfolio prioritisation.

Take the daily account reviews and synthesise into a ranked priority list
plus portfolio-level patterns. Sonnet (mid-tier) because synthesis across
many signals is where quality matters most.
"""
import json

from src.claude_client import ClaudeClient


def run(client: ClaudeClient, account_reviews: list[dict]) -> dict:
    compact = []
    for r in account_reviews:
        if "_parse_error" in r:
            continue
        compact.append({
            "account_id": r.get("account_id"),
            "health_delta": r.get("health_delta"),
            "primary_risk": r.get("primary_risk"),
            "primary_opportunity": r.get("primary_opportunity"),
            "attention_needed": r.get("attention_needed"),
            "attention_reason": r.get("attention_reason"),
            "confidence": r.get("confidence"),
        })
    user_content = (
        "Daily account reviews (one row per account):\n\n"
        + json.dumps(compact, indent=2)
    )
    return client.call(
        stage="prioritization",
        tier="mid",
        system_prompt_name="prioritization",
        user_content=user_content,
        max_tokens=800,
    )
