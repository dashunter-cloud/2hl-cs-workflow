"""Per-stage token + cost telemetry.

Every Claude API call is logged with stage, model, in/out tokens, USD cost.
Aggregated into outputs/telemetry.jsonl during a run, and into
outputs/cost_summary.json at run end.

Pricing is the placeholder reference from the Token Math Sheet:
    Low-cost ("Haiku" tier):  $0.15 / $0.60 per M tokens (in/out)
    Mid ("Sonnet" tier):       $0.80 / $3.20 per M tokens
    High ("Opus" tier):        $3.00 / $12.00 per M tokens
    Embed:                    $0.10 / $0.00 per M tokens

These are the prices used in the Token Math Sheet, NOT live Anthropic pricing.
This keeps the implementation's measured costs consistent with the sheet.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

PRICING = {
    "low":  {"in": 0.15, "out": 0.60},
    "mid":  {"in": 0.80, "out": 3.20},
    "high": {"in": 3.00, "out": 12.00},
    "embed":{"in": 0.10, "out": 0.00},
}

# Map our tier names to actual Anthropic model IDs.
# Haiku 4.5 is the cheapest production model available; we use Sonnet 4.6
# for mid-tier work and reserve Opus 4.7 for the high-reasoning stages.
MODEL_FOR_TIER = {
    "low":  "claude-haiku-4-5-20251001",
    "mid":  "claude-sonnet-4-6",
    "high": "claude-opus-4-7",
}


@dataclass
class StageCall:
    run_id: str
    stage: str
    tier: str
    model: str
    in_tokens: int
    out_tokens: int
    cost_usd: float
    latency_ms: int
    ts: float


def cost_for(tier: str, in_tokens: int, out_tokens: int) -> float:
    p = PRICING[tier]
    return (in_tokens * p["in"] + out_tokens * p["out"]) / 1_000_000


class Telemetry:
    """Append-only JSONL log of every API call, plus in-memory aggregation."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.calls: list[StageCall] = []

    def record(self, call: StageCall) -> None:
        self.calls.append(call)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(call)) + "\n")

    def summary(self) -> dict:
        """Aggregate by stage: total cost, total tokens, call count, avg cost."""
        by_stage: dict[str, dict] = {}
        for c in self.calls:
            s = by_stage.setdefault(c.stage, {
                "calls": 0, "in_tokens": 0, "out_tokens": 0,
                "total_cost_usd": 0.0, "tier": c.tier, "model": c.model,
            })
            s["calls"] += 1
            s["in_tokens"] += c.in_tokens
            s["out_tokens"] += c.out_tokens
            s["total_cost_usd"] += c.cost_usd
        for s in by_stage.values():
            s["avg_cost_per_call_usd"] = (
                s["total_cost_usd"] / s["calls"] if s["calls"] else 0
            )
            s["avg_in_tokens"] = s["in_tokens"] / s["calls"] if s["calls"] else 0
            s["avg_out_tokens"] = s["out_tokens"] / s["calls"] if s["calls"] else 0
        return {
            "by_stage": by_stage,
            "total_cost_usd": sum(c.cost_usd for c in self.calls),
            "total_calls": len(self.calls),
        }
