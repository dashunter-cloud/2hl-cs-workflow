"""Stage 1: Daily account-health scan.

For each account in the portfolio, produce a structured review flagging
risk and opportunity. This is the cheap, high-volume stage. Haiku.

Parallelised across accounts because they are independent.
"""
from concurrent.futures import ThreadPoolExecutor

from src.claude_client import ClaudeClient
from src.data_loader import CSData


def _one(client: ClaudeClient, data: CSData, aid: str) -> dict:
    ctx = data.account_context(aid)
    result = client.call(
        stage="account_review",
        tier="low",
        system_prompt_name="account_review",
        user_content=ctx,
        max_tokens=400,
    )
    if "_parse_error" in result:
        result["account_id"] = aid
    return result


def run(client: ClaudeClient, data: CSData, account_ids: list[str]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda aid: _one(client, data, aid), account_ids))
