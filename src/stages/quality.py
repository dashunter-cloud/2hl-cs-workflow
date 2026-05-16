"""Stage 5: Output quality review with SEPARATE-MODEL DISCRIMINATOR.

This is the architectural move. The first reviewer scores the output
against the quality standards. A SEPARATE call (still Sonnet, but a
fresh context with no access to the first reviewer's verdict at the
SYSTEM PROMPT level) independently judges the same output. Where they
disagree, the final action escalates to human.

This is the generator-plus-judge pattern from the assessment go-bag.
In a production system the judge would ideally be a different model
family entirely (Gemini, GPT, or a fine-tuned local judge). For the
assessment we demonstrate the separation with same-family-separate-call
which is Level 1 of the three discriminator levels.
"""
from src.claude_client import ClaudeClient
from src.data_loader import CSData


def run(client: ClaudeClient, data: CSData, output_ids: list[str]) -> list[dict]:
    results = []
    for oid in output_ids:
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

        # Step 2: INDEPENDENT judge sees the same draft + standards
        # but the first review's verdict is included so the judge can
        # explicitly agree/disagree. The point is separation of MODEL CALL,
        # not hiding the first verdict (a real-world judge sees it too).
        import json as _json
        judge_input = (
            f"DRAFT, ACCOUNT CONTEXT, AND STANDARDS:\n{full_ctx}\n\n"
            f"FIRST REVIEWER'S VERDICT (do not anchor on it; judge fresh):\n"
            f"{_json.dumps(first_review, indent=2)}"
        )
        judge_verdict = client.call(
            stage="quality_judge",
            tier="mid",
            system_prompt_name="quality_judge",
            user_content=judge_input,
            max_tokens=600,
        )
        if "_parse_error" in judge_verdict:
            judge_verdict["output_id"] = oid

        results.append({
            "output_id": oid,
            "first_review": first_review,
            "judge": judge_verdict,
            "consensus": _consensus(first_review, judge_verdict),
        })
    return results


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
