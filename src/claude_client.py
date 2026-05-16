"""Thin wrapper around the Anthropic SDK with tier routing + telemetry.

The client never selects the model itself; the caller passes a tier
("low", "mid", "high") and the client routes. This makes the cost-tier
routing decision visible at every call site and easy to audit.
"""
from __future__ import annotations

import json
import time
import os
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from src.telemetry import (
    Telemetry, StageCall, cost_for, MODEL_FOR_TIER,
)


class ClaudeClient:
    def __init__(self, telemetry: Telemetry, run_id: str):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.telemetry = telemetry
        self.run_id = run_id
        self._prompt_cache: dict[str, str] = {}

    def _load_prompt(self, name: str) -> str:
        if name not in self._prompt_cache:
            path = Path(__file__).parent.parent / "prompts" / f"{name}.md"
            self._prompt_cache[name] = path.read_text()
        return self._prompt_cache[name]

    def call(
        self,
        *,
        stage: str,
        tier: str,
        system_prompt_name: str,
        user_content: str,
        max_tokens: int = 1024,
    ) -> dict:
        """Run a single Claude call. Returns parsed JSON if possible, else
        a dict with {"raw": "..."} on parse failure.
        """
        system_prompt = self._load_prompt(system_prompt_name)
        model = MODEL_FOR_TIER[tier]
        t0 = time.monotonic()

        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        in_tokens = resp.usage.input_tokens
        out_tokens = resp.usage.output_tokens
        cost = cost_for(tier, in_tokens, out_tokens)

        self.telemetry.record(StageCall(
            run_id=self.run_id,
            stage=stage,
            tier=tier,
            model=model,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            ts=time.time(),
        ))

        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Strip common fence patterns if the model added them
            cleaned = text.strip()
            for fence in ("```json", "```"):
                if cleaned.startswith(fence):
                    cleaned = cleaned[len(fence):].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return {"_parse_error": True, "raw": text}
