"""Stage 1: Daily account-health scan.

For each account in the portfolio, produce a structured review flagging
risk and opportunity. This is the cheap, high-volume stage. Haiku.
"""
from src.claude_client import ClaudeClient
from src.data_loader import CSData


def run(client: ClaudeClient, data: CSData, account_ids: list[str]) -> list[dict]:
    reviews = []
    for aid in account_ids:
        ctx = data.account_context(aid)
        result = client.call(
            stage="account_review",
            tier="low",
            system_prompt_name="account_review",
            user_content=ctx,
            max_tokens=400,
        )
        # Defensive: ensure account_id present even on parse error
        if "_parse_error" in result:
            result["account_id"] = aid
        reviews.append(result)
    return reviews
