"""Stage 4: Customer check-in preparation.

For each scheduled check-in, build a brief that pulls forward prior call
notes, open tickets, usage trend, and the explicit topics for the call.
Sonnet (mid-tier) because the synthesis across multiple sources is where
hallucination risk lives.

Follow-up generation is the same pattern run after the call; for the
assessment we simulate it by running a "follow-up" variant with a
narrower prompt.
"""
from concurrent.futures import ThreadPoolExecutor

from src.claude_client import ClaudeClient
from src.data_loader import CSData


def _one(client: ClaudeClient, data: CSData, cid: str) -> dict:
    ctx = data.checkin_context(cid)
    brief = client.call(
        stage="checkin_prep",
        tier="mid",
        system_prompt_name="checkin_prep",
        user_content=ctx,
        max_tokens=900,
    )
    if "_parse_error" in brief:
        brief["checkin_id"] = cid
    return brief


def run(client: ClaudeClient, data: CSData, checkin_ids: list[str]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda cid: _one(client, data, cid), checkin_ids))
