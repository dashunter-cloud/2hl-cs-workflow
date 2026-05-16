# 2HL AI System Design Assessment — Customer Success Workflow

End-to-end AI workflow simulation for a B2B SaaS customer success function. Built for the 2HL / Crossover Head of Academics AI System Design Assessment, 16 May 2026.

The workflow handles seven core operational areas for a 750-account portfolio within a fixed $50,000/year token budget. The implementation runs on the provided 18-account synthetic dataset and produces measured token and cost data for every workflow stage.

## Architecture in one breath

A cost-tiered pipeline. Cheap models do high-volume scanning and routing. Mid-tier models do synthesis where quality matters. The high-tier model is reserved for the lowest-frequency stage (segment-level intervention design). The quality-review stage uses a SEPARATE-CALL DISCRIMINATOR (a second independent judge) so the system fails noisily on disagreement rather than silently certifying weak outputs.

This is the same architectural pattern I use across Kickstone's products (Sonny Jim, DISCOVER, KS Rapport): generator plus judge, calibration gates between stages, route by cost-tier with deterministic policy at the boundaries.

## Workflow stages

| # | Stage | Tier | Trigger | What it does |
|---|---|---|---|---|
| 1 | Account review | low (Haiku) | Daily, per account | Flags risk and opportunity signals from CRM + usage + tickets |
| 2 | Prioritisation | mid (Sonnet) | Daily, once per portfolio | Synthesises reviews into a ranked attention list plus portfolio patterns |
| 3 | Inbound triage | low (Haiku) | Per ticket | Routes to immediate / scheduled / escalation with a drafted response |
| 4 | Check-in prep | mid (Sonnet) | Per scheduled check-in | Builds a brief that carries forward open follow-ups + relevant context |
| 5 | Quality review + judge | mid (Sonnet) gen + low (Haiku) judge | Per draft output | First reviewer (Sonnet) scores against quality standards; a separate-MODEL judge (Haiku) independently verifies. Different model = real discriminator separation, cheaper, and dodges Sonnet rate-limit. Disagreement triggers escalation |
| 6 | Intervention design | high (Opus) | Bi-weekly, conditional | Deterministic detector spots segment-level decline; LLM designs a corrective plan with success metric |
| 7 | Routing | free (deterministic) | After every cycle | Applies policy: builds work queues and counts human escalations |

## How to run

Requires Python 3.11+ and an Anthropic API key.

```bash
git clone <repo-url>
cd 2hl-cs-workflow

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your ANTHROPIC_API_KEY

# Smoke test (one run, 3 accounts only, ~30 seconds, ~$0.07):
python run.py --once --sample-accounts 3

# Full assessment runs (5 representative end-to-end runs on the full synthetic sample):
python run.py --runs 5
```

## Outputs

After running, see:

- `outputs/run_<N>/account_reviews.json` - daily health reviews per account
- `outputs/run_<N>/priorities.json` - prioritised work list + portfolio patterns
- `outputs/run_<N>/inbound_triages.json` - ticket triage with draft responses
- `outputs/run_<N>/checkin_briefs.json` - check-in preparation packets
- `outputs/run_<N>/quality_reviews.json` - first review + independent judge + consensus
- `outputs/run_<N>/intervention.json` - segment-level corrective plan (when triggered)
- `outputs/run_<N>/routing.json` - work-queue assignments
- `outputs/run_<N>/run_summary.json` - token + cost telemetry for the run
- `outputs/telemetry.jsonl` - append-only log of every API call
- `outputs/cost_summary.json` - aggregate across all runs

## Repository layout

```
2hl-cs-workflow/
├── README.md                    # this file
├── requirements.txt             # anthropic, pandas, python-dotenv
├── run.py                       # single entry point
├── .env.example
├── data/                        # provided synthetic dataset
│   ├── accounts.csv
│   ├── usage_events.csv
│   ├── support_tickets.csv
│   ├── call_notes.csv
│   ├── scheduled_checkins.csv
│   ├── junior_outputs.csv
│   └── quality_standards.csv
├── prompts/                     # system prompts as on-disk artefacts
│   ├── account_review.md
│   ├── prioritization.md
│   ├── inbound_routing.md
│   ├── checkin_prep.md
│   ├── quality_review.md
│   ├── quality_judge.md         # the separate-model discriminator
│   └── intervention_design.md
├── src/
│   ├── claude_client.py         # Anthropic wrapper + tier routing + telemetry
│   ├── data_loader.py           # CSV → per-account context bundles
│   ├── telemetry.py             # token + cost logging (uses sheet's pricing tiers)
│   ├── pipeline.py              # orchestrator
│   └── stages/                  # one file per workflow stage
└── outputs/
    ├── telemetry.jsonl
    ├── cost_summary.json
    └── run_<N>/*.json
```

## Design decisions

**Why cost-tiered routing.** A $50k/year budget at 750-account scale forces honest model selection. Pricing tiers from the assessment Token Math Sheet are: low $0.15/$0.60 per M tokens, mid $0.80/$3.20 per M, high $3.00/$12.00 per M. Daily account scan is 750 calls/day; running that on the high tier alone would consume the budget in weeks. We route the high-volume scan to Haiku, the synthesis stages to Sonnet, and only the bi-weekly intervention design to Opus.

**Why a separate-call judge for quality review.** The most failure-prone stage is "did the AI just confidently produce something wrong?" A single model marking its own work has the same blind spots that produced the work. A separate-call discriminator catches mismatches; disagreement is escalated to a human. This pattern is in production in KS Rapport and the A-Level Biology tutor at Kickstone. Same shape, different vertical.

**Why deterministic routing.** Policy decisions (which queue does this ticket go in, which CSM owns it) are deterministic rules, not LLM calls. Free at runtime, easy to audit, easy to change. The LLM upstream produced the recommendation; the routing stage applies the policy.

**Where I'd take this in production.** Production would add: (a) prompt caching for the ~80% of system prompt that's static, dramatically reducing cost (this is the biggest single lever — Haiku 4.5 with caching at ~84% hit rate is the Sonny Jim reference floor of about a penny per call); (b) a different-vendor judge (Gemini or a fine-tuned local model) instead of same-vendor different-model Haiku, for full lineage separation; (c) blind-judge variant for the quality stage to remove anchoring (judge scores draft fresh, then deterministic code compares against first reviewer); (d) embeddings-based memory retrieval rather than full account context per call; (e) Postgres-backed audit log per Sonny's MCP-pattern registry; (f) hierarchical prioritisation at 750-account scale (per-segment then per-account) to avoid attention dilution in a single mega-prompt; (g) webhook intake + SLA clock for true 24/7 responsiveness (today this is simulated batch execution); (h) per-ticket escalation packet generation as a dedicated Sonnet call.

## Evidence packet (measured, 5 representative end-to-end runs)

| Metric | Value |
|---|---|
| End-to-end runs completed | 5 / 5 |
| Total cost across runs (real Anthropic API) | $0.43 |
| Avg cost per end-to-end run | $0.086 |
| Projected annual cost at 750-account scale | $1,361 |
| Annual budget | $50,000 |
| Budget headroom | 97.3% |
| Calls per stage (5 runs aggregate) | account_review 90, prioritization 5, inbound_triage 60, checkin_prep 60, quality_review 40, quality_judge 40, intervention_design 5 |
| Ticket escalations triggered (5 runs aggregate) | 43 of 60 triages (~72%) — high-severity unresolved cluster in synthetic data |
| Quality-review escalations | 9 of 40 (22.5%) — judge disagreement with generator caught real quality issues |
| Parse errors by stage (5 runs aggregate) | checkin_prep 4, inbound_triage 2, others 0 — ~2% overall; handled by escalation, not silent retry |
| Intervention triggered | 5 / 5 runs (segment-level decline detected; deterministic detector) |

## Known limitations (raised by external code review)

External code review pass with Codex (gpt-5.5) and Gemini 3 Pro flagged the following. Each is captured in code comments and the session log.

1. **Judge anchoring.** The Haiku judge sees the first reviewer's verdict in the user prompt. Even with a "do not anchor" instruction in the judge's system prompt, this creates anchoring risk. Production upgrade: blind judge (judge scores draft fresh, then deterministic code compares).
2. **24/7 responsiveness is simulated batch execution.** No webhook intake, no SLA clock, no after-hours policy. Production would add a queue runner and notification hooks.
3. **Prioritisation at 750-account scale.** A single Sonnet call with all 750 reviews would push 150k+ input tokens and risk attention dilution. Production would shift to hierarchical prioritisation (segment-first, then accounts within segments).
4. **Same-vendor judge.** Haiku judging Sonnet is structural separation (different size, different post-training) but stays within Anthropic. True lineage separation needs a different vendor family.

## A note on model IDs

`telemetry.py` references `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, and `claude-opus-4-7`. These are the current account-available model IDs at the time of this assessment (May 2026). External code review queried these against earlier Anthropic documentation snapshots; the 5-run end-to-end execution against the live Anthropic API confirms they are valid.

## License

Built for assessment purposes. Not for redistribution.
