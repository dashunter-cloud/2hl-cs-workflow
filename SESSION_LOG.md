# Submission C - AI Build Process Memo

**Candidate:** David Hunter
**Email:** dashunter@gmail.com
**Date submitted:** 16 May 2026
**Starter project version:** Synthetic CS dataset (8 CSVs)
**Other AI tools used, if any:** None during the assessment. Claude Code (Sonnet 4.6) was the sole AI building partner.

---

## 1. Workflow Decomposition

I split the customer success operating scope into seven concrete pipeline stages that map directly to the operating areas in the brief: (1) daily account-health review per account, (2) portfolio prioritisation across all reviews, (3) inbound ticket triage and routing, (4) check-in preparation, (5) output quality review with a SEPARATE-CALL JUDGE, (6) targeted intervention design at segment level, (7) deterministic routing to resolution / follow-up / escalation queues.

I prioritised the architecture choice first: a cost-tiered pipeline with Haiku for the high-volume scan stages, Sonnet for the synthesis stages, and Opus reserved for the lowest-frequency highest-stakes stage (segment intervention). The biggest design move is using a SEPARATE Claude call as an independent judge on the quality-review stage. A single model marking its own work has the same blind spots that produced the work. A second independent call catches genuine quality failures and escalates disagreement to a human. This is the same generator-plus-judge pattern I use at Kickstone (DISCOVER's three-stage pipeline, KS Rapport's call analysis, the A-level Biology tutor's mastery discriminator).

Simplifications I made deliberately for the assessment:
- The judge is same-model-family-separate-call. In production I would use a different model family (Gemini or a fine-tuned local judge) for true lineage separation. The architecture supports the swap; only the tier routing changes.
- Memory retrieval is in-process pandas filtering, not a real vector DB. Token math counts the context-assembly cost honestly so the sheet's "memory retrieval" row maps to a real workload.
- Embedding / retrieval costs zero in this implementation because I assemble context deterministically. In production this would be a vector lookup plus a token charge.

## 2. Claude Code Usage Summary

Claude Code (running in my Sonny Jim repo) was the primary building partner across the 90 minutes. I directed it to:

- Read all 8 provided CSVs in one parallel batch to understand the dataset shape before writing any code.
- Scaffold the project directory (`2hl-cs-workflow/`) with `data/`, `prompts/`, `src/stages/`, `outputs/`, plus requirements.txt, .env.example, and a comprehensive README.
- Write seven on-disk system prompts (one per workflow stage) following the spec-as-prompt pattern.
- Build a `ClaudeClient` wrapper that takes a tier parameter, looks up the correct model, makes the API call, and logs every call's tokens and cost to `outputs/telemetry.jsonl`.
- Build the seven stage modules with consistent structure (each exports a `run()` function taking the client + data + stage-specific inputs).
- Build the orchestrator `pipeline.py` and the entry point `run.py`.
- Run a smoke test (1 run, 3 accounts) before going to full scale.

Where I made decisions myself:
- The architectural shape (cost-tiered + separate-call judge + deterministic routing). This was a direct application of patterns from a prepared go-bag rather than something Claude Code generated from scratch.
- The pricing alignment: my telemetry uses the SHEET'S placeholder tier prices (low $0.15/$0.60, mid $0.80/$3.20, high $3.00/$12.00), not real Anthropic prices, so the implementation's measured cost lines up with the sheet's numbers.
- The quality-review threshold logic in `_consensus()` (escalate on parse error, escalate on disagree, ship on agree+pass).

I reviewed every output before accepting it:
- The smoke test caught a `max_tokens=700` truncation bug on the quality-review stage. The model was producing excellent grounded scoring (with specific reference to the $240k contract value, the 9-tickets-in-30-days signal, the renewal date) but the JSON was being clipped mid-response. I bumped the limit to 1500 for quality-review and 600 for the judge.
- I spot-checked the prioritisation output: A002 (BrightPath Logistics) was correctly ranked top with a concrete reason about the unresolved high-severity integration ticket. A003 (Cobalt Health) was correctly identified as a time-sensitive expansion opportunity.

## 3. Key Prompts or Instructions

| Prompt / instruction summary | Goal | Claude Code output | Accept / revise / reject | Why |
|---|---|---|---|---|
| Read all 8 CSVs in parallel to understand the dataset shape | Get full data picture in one batch | Read all 8 files; surfaced the 18-account / 12-ticket / 12-checkin / 8-output / 6-standards shape | Accepted | Right call; established scaling math (sample to 750 accounts) immediately |
| Build a ClaudeClient that takes a tier param and routes to the correct model. Telemetry logs every call's tokens and cost to JSONL | Make cost discipline a structural property | Telemetry class + StageCall dataclass + tier-to-model mapping | Accepted | Clean abstraction; every call site has to declare its tier, which makes cost decisions visible at review time |
| The quality stage runs TWO Claude calls: a first reviewer scores, then a separate judge independently verifies. Where they disagree, escalate to human | The architectural move: generator-plus-judge | quality.py implements `first_review` and `judge_verdict` with a `_consensus()` policy | Accepted | This is the load-bearing distinctive move in the whole system |
| All prompts on disk in prompts/*.md. Each stage loads its prompt by name | Spec-as-prompt pattern. Role lives on disk not in code | claude_client._load_prompt caches and loads .md files | Accepted | Means prompts are reviewable artefacts, not buried strings |
| Bump max_tokens to 1500 for quality_review and 600 for quality_judge | Fix truncation bug found in smoke test | Edit applied; reran successfully | Accepted (after revision) | Smoke test was the catch; the output was great content being clipped |

## 4. Debugging and Iteration

| Issue | How I found it | How I fixed it | Claude Code's role |
|---|---|---|---|
| `pip install anthropic` blocked by PEP 668 | First install attempt failed | Created `.venv` and installed inside | Diagnosed the error message immediately, recommended venv |
| `ModuleNotFoundError: dotenv` | First `python run.py` attempt | Added `python-dotenv` to requirements + pip install | Caught at smoke-test stage, not at final-run stage |
| Quality review parse errors on all 8 outputs (smoke test) | Spot-check of `quality_reviews.json` after smoke run | Bumped `max_tokens` from 700 to 1500 | Diagnosed via `repr(raw)` inspection - found the response was excellent but truncated mid-JSON because the scoring rationales were verbose |
| Intervention not triggering on smoke run with 3 accounts | Inspecting `intervention.json` showed `segment_issue_detected: false` | This was correct behaviour: only 2 accounts in the 3-sample shared a declining-trend signal across different segments. Full 5-run on 18 accounts produced the expected result | Caught at output-inspection step, not silently passed |

## 5. Design Decisions

**Cost-tiered routing.** $50k/year divided by 260 working days is about $192/day total budget. Daily account scan alone is 750 calls per day. Running all 750 on Sonnet would burn the budget on that single stage. Routing the scan to Haiku ($0.15/$0.60) drops the cost roughly 5x versus Sonnet ($0.80/$3.20) and ~20x versus Opus ($3.00/$12.00). The high-cost Opus tier is only invoked for segment-intervention design, which fires bi-weekly.

**Separate-call discriminator on quality review.** This is the architectural move. Asking a model to mark its own output gives you the same blind spots that produced the output. The implementation uses two separate Claude calls with shared context but no shared output context. The judge sees the first reviewer's verdict (so it can explicitly agree / disagree) but is instructed not to anchor. Disagreement triggers escalation to human. Production version would swap the judge to a different model family.

**Deterministic routing as a zero-cost stage.** The routing decision (immediate / scheduled / escalation, plus owner) is a policy on the LLM upstream's recommendations. Running this in plain Python keeps it free at runtime, easy to audit, and changeable without redeploying prompts.

**Prompt budget discipline in the prompts themselves.** Every prompt ends with "Output ONLY the JSON object." This trims output tokens, which matter more than input tokens at our pricing (output tokens are 3-4x the price of input across all tiers). It also makes parsing reliable, reducing the retry / recheck rate (which the Token Math Sheet has as the J column).

**Pricing alignment.** My telemetry uses the Token Math Sheet's placeholder pricing tiers, not real Anthropic prices. This means measured costs in `cost_summary.json` are directly comparable to the sheet's per-stage cost figures and the $50k budget.

**Simplifications.** Memory retrieval is in-process pandas filtering (zero LLM cost), so the "memory/context retrieval" row in the sheet reflects the embedding-tier cost we'd pay in production rather than what I implemented today. Prompt caching is not yet enabled; in production this would reduce input-token costs on the daily scan dramatically (Haiku 4.5 with prompt caching at ~84% hit rate is the Sonny Jim reference floor of about a penny per call).

## 6. Validation

I validated the implementation in three layers:

**Layer 1 - smoke test.** `python run.py --once --sample-accounts 3` runs the full pipeline on a 3-account sample in about 30 seconds. This caught the max_tokens truncation bug on the quality-review stage before I committed to a full 5-run.

**Layer 2 - output inspection.** After the smoke test I inspected three specific outputs to verify the implementation was producing meaningful work:
- `account_reviews.json`: confirmed account A002 was correctly flagged as declining with attention_needed=true and a specific risk reason citing the integration sync failures.
- `priorities.json`: confirmed the top 3 accounts were ranked sensibly (A002 high-severity unresolved, A001 dual-track, A003 expansion opportunity).
- `quality_reviews.json` raw text: confirmed the model was scoring outputs with concrete grounding (referencing the $240k contract value, the 9-tickets-in-30-days, the specific renewal date).

**Layer 3 - aggregate cost verification.** The `cost_summary.json` produced after the full 5-run reports total cost and per-stage averages. I verified the per-stage costs match my predictions from the Token Math Sheet. The total annual cost projection scales from the measured per-run figures.

The 7-stage pipeline runs end-to-end with no failures across all 5 runs.

## 7. What I Would Improve With More Time

- **Prompt caching.** ~80% of every system prompt is static across calls within a run. Enabling prompt caching would reduce input-token costs on the daily scan stage roughly 4-5x, freeing budget for more frequent quality reviews or richer check-in context.
- **Different-family judge.** Swap the quality-review judge from Sonnet to Gemini or a fine-tuned local model so model lineage separation is real, not nominal. Same shape, just different model client.
- **Vector retrieval.** Account context is built deterministically today. In production with 750 accounts and historical depth, a vector store keyed on account_id + recency would let us fetch only the relevant slice of history per call, keeping input tokens flat as the corpus grows.
- **Eval set.** I would build a small held-out set of 5-10 quality reviews with known-good and known-bad outputs to track judge accuracy over time. Right now I trust the judge; in production I would measure it.
- **Postgres-backed audit log.** My telemetry is JSONL. In Sonny (Kickstone's WhatsApp PA) every tool call has a Postgres `ToolCall` row with input, output, status, and duration. Same pattern would apply here so a CSM lead can SQL-query what the agent did for any account last week.
- **Cost dashboard.** A simple stage-by-stage burn-rate view against the $50k annual budget, refreshed daily. Goes red when any stage runs hot.

## 8. Candidate Confirmation

I confirm that this memo accurately describes how I used Claude Code and any other AI tools while completing this assessment.

Name: David Hunter
Signature: David Hunter
Date: 16 May 2026

---

## Appendix - Files Claude Code Created or Modified

```
2hl-cs-workflow/
├── README.md                        (new)
├── requirements.txt                 (new)
├── .env.example                     (new)
├── .gitignore                       (new)
├── run.py                           (new)
├── data/                            (copied from provided dataset)
├── prompts/
│   ├── account_review.md            (new)
│   ├── prioritization.md            (new)
│   ├── inbound_routing.md           (new)
│   ├── checkin_prep.md              (new)
│   ├── quality_review.md            (new)
│   ├── quality_judge.md             (new)
│   └── intervention_design.md       (new)
└── src/
    ├── __init__.py                  (new)
    ├── claude_client.py             (new)
    ├── data_loader.py               (new)
    ├── telemetry.py                 (new)
    ├── pipeline.py                  (new)
    └── stages/
        ├── __init__.py              (new)
        ├── account_review.py        (new)
        ├── prioritization.py        (new)
        ├── inbound.py               (new)
        ├── checkin.py               (new)
        ├── quality.py               (new; max_tokens revised after smoke test)
        ├── intervention.py          (new)
        └── routing.py               (new)
```

All files created within the 90-minute assessment window. No external code copied. Architecture references Kickstone's production products (Sonny Jim, DISCOVER, KS Rapport) for pattern provenance but no code was lifted.
