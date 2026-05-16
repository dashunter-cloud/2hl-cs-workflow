"""Stage 5: Output quality review with SEPARATE-MODEL DISCRIMINATOR.

This is the architectural move. The first reviewer (Sonnet, mid-tier)
scores the output against the quality standards. A SEPARATE call on a
DIFFERENT MODEL (Haiku, low-tier) independently judges the same output.
Where they disagree, the final action escalates to human.

The judge being a structurally different model (different size, different
training run, different post-training) is the real separation, beyond
just being a separate API call. This is Level 1.5 of the three
discriminator levels (between same-family-separate-call and
different-vendor-family). Level 2 (different vendor family, e.g. Gemini
or a fine-tuned local judge) is the production upgrade path.

KNOWN LIMITATION (raised by external code review): the judge sees the
first reviewer's verdict in the user prompt, which creates anchoring
risk despite the "do not anchor" instruction in the judge's system
prompt. A blind-judge variant (judge scores draft fresh, then
deterministic code compares) is the cleanest fix and is in
docs/improvements as a follow-up.
"""
from src.claude_client import ClaudeClient
from src.data_loader import CSData


def _one(client: ClaudeClient, data: CSData, oid: str) -> dict:
    full_ctx, draft_text, standards_text = data.output_context(oid)

    # Step 1: first reviewer
    first_review = client.call(
        stage="quality_review",
        tier="mid",
        system_prompt_name="quality_review",
        user_content=full_ctx,
        max_tokens=1500,
    )
    if "_parse_error" in first_review:
        first_review["output_id"] = oid

    # Step 2: INDEPENDENT judge call. Sequential per-output (the judge sees
    # the first review's verdict so it can explicitly agree/disagree) but
    # parallel across outputs at the run() level.
    import json as _json
    judge_input = (
        f"DRAFT, ACCOUNT CONTEXT, AND STANDARDS:\n{full_ctx}\n\n"
        f"FIRST REVIEWER'S VERDICT (do not anchor on it; judge fresh):\n"
        f"{_json.dumps(first_review, indent=2)}"
    )
    # JUDGE IS A DIFFERENT MODEL (Haiku, not Sonnet).
    # The discriminator pattern is sharper when the judge is structurally
    # different from the generator: different training run, different
    # post-training. Cost-tier wise this is also the right move - the judge's
    # job is verification, not synthesis, so a cheaper model is fit-for-purpose.
    judge_verdict = client.call(
        stage="quality_judge",
        tier="low",
        system_prompt_name="quality_judge",
        user_content=judge_input,
        max_tokens=600,
    )
    if "_parse_error" in judge_verdict:
        judge_verdict["output_id"] = oid

    return {
        "output_id": oid,
        "first_review": first_review,
        "judge": judge_verdict,
        "consensus": _consensus(first_review, judge_verdict),
    }


def run(client: ClaudeClient, data: CSData, output_ids: list[str]) -> list[dict]:
    # Lower parallelism than other stages: each output triggers a Sonnet
    # first-review call which is the rate-limited tier in our org. Two-wide
    # gives a steady stream without tripping the 8k-output-tokens/min cap.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        return list(ex.map(lambda oid: _one(client, data, oid), output_ids))


def _consensus(first: dict, judge: dict) -> str:
    """Deterministic policy on the two reviews.

    - Both pass -> ship
    - Either flags escalate_to_human -> escalate
    - Judge disagrees -> escalate (mismatch is the signal)
    - Otherwise -> use judge's final_action
    """
    if first.get("_parse_error") or judge.get("_parse_error"):
        return "escalate (parse error)"
    if first.get("escalate_to_human"):
        return "escalate"
    if judge.get("judge_verdict") in ("disagree", "partial"):
        return "escalate"
    return judge.get("final_action", "review_needed")
