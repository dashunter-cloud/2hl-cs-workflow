"""End-to-end pipeline orchestrator.

A single end-to-end run walks through:
    1. account_review (18 accounts in synthetic sample, scales to 750)
    2. prioritization (one synthesis call across all reviews)
    3. inbound triage (12 tickets in sample, scales to ~6/day at 750-account portfolio)
    4. checkin prep (12 check-ins in sample, scales to ~2.4/day)
    5. quality review with separate-model judge (8 outputs)
    6. intervention design (deterministic detect, conditional LLM call)
    7. routing (deterministic, zero cost)

Each stage logs token counts + cost via Telemetry. The full per-run
output bundle is saved to outputs/run_N/*.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.claude_client import ClaudeClient
from src.data_loader import CSData
from src.telemetry import Telemetry
from src.stages import (
    account_review, prioritization, inbound, checkin, quality, intervention, routing,
)


def run_pipeline(run_id: str, *, sample_accounts: int | None = None,
                 sample_tickets: int | None = None,
                 sample_checkins: int | None = None,
                 sample_outputs: int | None = None,
                 output_dir: Path | None = None,
                 telemetry_path: Path | None = None) -> dict:
    """Execute one end-to-end run."""
    data = CSData()
    output_dir = output_dir or (Path("outputs") / f"run_{run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = telemetry_path or Path("outputs/telemetry.jsonl")
    telemetry = Telemetry(telemetry_path)

    client = ClaudeClient(telemetry, run_id)

    # Choose samples (default: full synthetic dataset)
    account_ids = data.accounts["account_id"].tolist()
    if sample_accounts:
        account_ids = account_ids[:sample_accounts]
    ticket_ids = data.tickets["ticket_id"].tolist()
    if sample_tickets:
        ticket_ids = ticket_ids[:sample_tickets]
    checkin_ids = data.checkins["checkin_id"].tolist()
    if sample_checkins:
        checkin_ids = checkin_ids[:sample_checkins]
    output_ids = data.outputs["output_id"].tolist()
    if sample_outputs:
        output_ids = output_ids[:sample_outputs]

    print(f"[run {run_id}] accounts={len(account_ids)} tickets={len(ticket_ids)} "
          f"checkins={len(checkin_ids)} outputs={len(output_ids)}")

    # Stage 1
    print(f"[run {run_id}] stage 1: account_review")
    reviews = account_review.run(client, data, account_ids)
    (output_dir / "account_reviews.json").write_text(json.dumps(reviews, indent=2))

    # Stage 2
    print(f"[run {run_id}] stage 2: prioritization")
    priorities = prioritization.run(client, reviews)
    (output_dir / "priorities.json").write_text(json.dumps(priorities, indent=2))

    # Stage 3
    print(f"[run {run_id}] stage 3: inbound triage")
    triages = inbound.run(client, data, ticket_ids)
    (output_dir / "inbound_triages.json").write_text(json.dumps(triages, indent=2))

    # Stage 4
    print(f"[run {run_id}] stage 4: checkin prep")
    checkin_briefs = checkin.run(client, data, checkin_ids)
    (output_dir / "checkin_briefs.json").write_text(json.dumps(checkin_briefs, indent=2))

    # Stage 5
    print(f"[run {run_id}] stage 5: quality review + judge")
    quality_results = quality.run(client, data, output_ids)
    (output_dir / "quality_reviews.json").write_text(json.dumps(quality_results, indent=2))

    # Stage 6
    print(f"[run {run_id}] stage 6: intervention design")
    intervention_result = intervention.run(client, data, reviews)
    (output_dir / "intervention.json").write_text(json.dumps(intervention_result, indent=2))

    # Stage 7
    print(f"[run {run_id}] stage 7: routing (deterministic)")
    routing_result = routing.run(triages, quality_results)
    (output_dir / "routing.json").write_text(json.dumps(routing_result, indent=2))

    # Run-level telemetry summary
    summary = telemetry.summary()
    run_summary = {
        "run_id": run_id,
        "stage_counts": {
            "accounts_reviewed": len(account_ids),
            "tickets_triaged": len(ticket_ids),
            "checkins_prepared": len(checkin_ids),
            "outputs_reviewed": len(output_ids),
        },
        "telemetry_summary": summary,
    }
    (output_dir / "run_summary.json").write_text(json.dumps(run_summary, indent=2))
    print(f"[run {run_id}] complete. total cost so far: ${summary['total_cost_usd']:.4f}")
    return run_summary
