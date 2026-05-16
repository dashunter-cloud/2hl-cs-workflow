"""Stage 7: Routing for resolution / follow-up / escalation.

DETERMINISTIC, NOT LLM-DRIVEN. Routing is a policy decision; the LLM
upstream already made the recommendation (route field on each triage
result). This stage applies the policy, produces the work-assignment
queues, and counts what would have been escalated to humans.

Cost: $0. Listed in telemetry as a free stage so the cost summary is
honest about what costs what.
"""
from collections import Counter


def run(triages: list[dict], quality_results: list[dict]) -> dict:
    by_route = Counter()
    by_owner = Counter()
    queues: dict[str, list[dict]] = {
        "immediate": [], "scheduled": [], "escalation": []
    }
    for t in triages:
        route = t.get("route", "scheduled")
        by_route[route] += 1
        by_owner[t.get("suggested_owner", "Unknown")] += 1
        if route in queues:
            queues[route].append({
                "ticket_id": t.get("ticket_id"),
                "account_id": t.get("account_id"),
                "urgency": t.get("urgency_score"),
                "reason": t.get("reason"),
            })

    quality_escalations = sum(
        1 for q in quality_results if q.get("consensus", "").startswith("escalate")
    )
    return {
        "ticket_routing": dict(by_route),
        "owner_distribution": dict(by_owner),
        "ticket_queues": queues,
        "quality_review_escalations": quality_escalations,
    }
