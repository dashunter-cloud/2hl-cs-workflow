"""Stage 3: Inbound ticket triage + draft.

Two-step:
- triage: Haiku categorises route (immediate/scheduled/escalation)
  and drafts a short response if not escalation.
- For escalations, we don't draft a customer-facing response; we
  defer to the escalation packet stage (handled by intervention.py).

This is the implementation of cost-tiered routing: cheap triage for
the high-volume operation; the more expensive synthesis only fires
when the triage flags it.
"""
from concurrent.futures import ThreadPoolExecutor

from src.claude_client import ClaudeClient
from src.data_loader import CSData


def _one(client: ClaudeClient, data: CSData, tid: str) -> dict:
    ctx = data.ticket_context(tid)
    triage = client.call(
        stage="inbound_triage",
        tier="low",
        system_prompt_name="inbound_routing",
        user_content=ctx,
        max_tokens=400,
    )
    if "_parse_error" in triage:
        triage["ticket_id"] = tid
    return triage


def run(client: ClaudeClient, data: CSData, ticket_ids: list[str]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda tid: _one(client, data, tid), ticket_ids))
