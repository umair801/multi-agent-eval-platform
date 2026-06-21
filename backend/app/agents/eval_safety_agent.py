# ============================================================
# AgAI_31: Eval/Safety Agent
# Scores every conversation turn across 5 dimensions
# ============================================================

import time
import uuid
import json
import structlog
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.models import AgentState, EvalScores
from app.tools.llm import invoke_with_fallback
from app.observability.tracer import build_trace_step, get_supabase

logger = structlog.get_logger()

# ============================================================
# EVAL SCORING PROMPT
# ============================================================

EVAL_SYSTEM_PROMPT = """You are an evaluation agent for a multi-agent customer support AI platform.

Your job is to score the quality of a completed conversation turn across 5 dimensions.
Each score is a float between 0.0 (complete failure) and 1.0 (perfect).

Scoring dimensions:

1. task_success: Did the response fully address the user's question or request?
   1.0 = fully resolved | 0.5 = partially resolved | 0.0 = not resolved

2. grounding_accuracy: Is the response grounded only in provided context (billing data, policy excerpts, tool results)?
   1.0 = fully grounded | 0.5 = mostly grounded, minor hallucination | 0.0 = hallucinated

3. tool_correctness: Were the right tools called with correct parameters?
   1.0 = correct tools called | 0.5 = tools called but suboptimal | 0.0 = wrong tools or missing calls
   N/A (1.0) if no tools were needed.

4. policy_compliance: Does the response comply with stated policies (refund window, SLA, cancellation)?
   1.0 = fully compliant | 0.5 = minor deviation | 0.0 = policy violation

5. escalation_correctness: Was the escalation decision correct?
   1.0 = correct decision | 0.5 = borderline | 0.0 = wrong decision
   N/A (1.0) if no escalation decision was made.

Also identify:
- failure_category: wrong_intent | missing_tool | hallucination | wrong_escalation | policy_violation | none
- flagged_for_review: true if any score is below 0.6, false otherwise
- eval_notes: one sentence summary of the main issue (or "No issues detected.")

Respond in this EXACT format (valid JSON only, no markdown):
{
  "task_success": 0.0,
  "grounding_accuracy": 0.0,
  "tool_correctness": 0.0,
  "policy_compliance": 0.0,
  "escalation_correctness": 0.0,
  "failure_category": "none",
  "flagged_for_review": false,
  "eval_notes": "No issues detected."
}
"""


# ============================================================
# EVAL/SAFETY AGENT NODE
# ============================================================

def eval_safety_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: scores the completed conversation turn
    and writes eval results to Supabase.
    """
    conversation_id  = state.get("conversation_id", "unknown")
    turn_id          = state.get("turn_id", 0)
    user_message     = state.get("user_message", "")
    intent           = state.get("intent", "general")
    final_response   = state.get("final_response", "")
    billing_context  = state.get("billing_context", "")
    policy_excerpts  = state.get("policy_excerpts") or []
    tool_results     = state.get("tool_results") or []
    grounding_sources= state.get("grounding_sources") or []
    pending_approvals= state.get("pending_approval_ids") or []
    errors           = state.get("errors") or []

    logger.info("eval_safety_agent_start", conversation_id=conversation_id)

    trace_steps = []

    # --------------------------------------------------------
    # Build eval context for scoring
    # --------------------------------------------------------
    tool_summary = json.dumps([
        {
            "tool_name": tr.get("tool_name"),
            "status":    tr.get("status"),
            "output":    tr.get("tool_output"),
        }
        for tr in tool_results
    ], indent=2) if tool_results else "No tools called."

    policy_summary = "\n".join([
        f"[{e.get('source')}] {e.get('text', '')[:100]}..."
        for e in policy_excerpts[:3]
    ]) if policy_excerpts else "No policy excerpts retrieved."

    eval_context = f"""USER MESSAGE: {user_message}

CLASSIFIED INTENT: {intent}

BILLING CONTEXT PROVIDED:
{billing_context[:500] if billing_context else 'None'}

POLICY EXCERPTS USED:
{policy_summary}

TOOL CALLS MADE:
{tool_summary}

PENDING APPROVALS: {pending_approvals}

FINAL RESPONSE GIVEN TO CUSTOMER:
{final_response}

ERRORS DURING EXECUTION: {errors if errors else 'None'}

Score this conversation turn."""

    messages = [
        SystemMessage(content=EVAL_SYSTEM_PROMPT),
        HumanMessage(content=eval_context),
    ]

    start = time.time()
    try:
        response, model_used, latency_ms, tokens_in, tokens_out, cost = invoke_with_fallback(
            messages=messages,
            temperature=0.0,
            context="eval_safety_agent",
        )

        # --------------------------------------------------------
        # Parse eval scores from JSON response
        # --------------------------------------------------------
        raw_content = response.content.strip()

        # Strip markdown fences if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]

        scores_dict = json.loads(raw_content.strip())

        eval_scores = EvalScores(
            task_success=           scores_dict.get("task_success", 0.5),
            grounding_accuracy=     scores_dict.get("grounding_accuracy", 0.5),
            tool_correctness=       scores_dict.get("tool_correctness", 1.0),
            policy_compliance=      scores_dict.get("policy_compliance", 0.5),
            escalation_correctness= scores_dict.get("escalation_correctness", 1.0),
            avg_latency_ms=         state.get("total_latency_ms", 0),
            total_cost_usd=         state.get("total_cost_usd", 0.0),
            flagged_for_review=     scores_dict.get("flagged_for_review", False),
            failure_category=       scores_dict.get("failure_category", "none"),
            eval_notes=             scores_dict.get("eval_notes", ""),
        )

        # Auto-flag if any score below 0.6
        if any([
            eval_scores.task_success < 0.6,
            eval_scores.grounding_accuracy < 0.6,
            eval_scores.tool_correctness < 0.6,
            eval_scores.policy_compliance < 0.6,
            eval_scores.escalation_correctness < 0.6,
        ]):
            eval_scores.flagged_for_review = True

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="eval_safety",
            step_type="model_response",
            prompt_text=eval_context,
            model_response=raw_content,
            latency_ms=latency_ms,
            token_count_input=tokens_in,
            token_count_output=tokens_out,
            cost_usd=cost,
        ))

        # --------------------------------------------------------
        # Write eval results to Supabase
        # --------------------------------------------------------
        _write_eval_results(
            conversation_id=conversation_id,
            eval_scores=eval_scores,
            model=model_used,
        )

        logger.info(
            "eval_safety_agent_complete",
            conversation_id=conversation_id,
            flagged=eval_scores.flagged_for_review,
            failure_category=eval_scores.failure_category,
            task_success=eval_scores.task_success,
        )

        return {
            **state,
            "eval_scores":      eval_scores.model_dump(),
            "flagged_for_review": eval_scores.flagged_for_review,
            "failure_category": eval_scores.failure_category,
            "total_tokens_in":  state.get("total_tokens_in", 0) + tokens_in,
            "total_tokens_out": state.get("total_tokens_out", 0) + tokens_out,
            "total_cost_usd":   state.get("total_cost_usd", 0.0) + cost,
            "total_latency_ms": state.get("total_latency_ms", 0) + latency_ms,
            "trace_steps":      trace_steps,
        }

    except json.JSONDecodeError as e:
        logger.error("eval_scores_parse_failed", error=str(e), raw=response.content[:200])

        default_scores = EvalScores(
            task_success=0.5,
            grounding_accuracy=0.5,
            tool_correctness=1.0,
            policy_compliance=0.5,
            escalation_correctness=1.0,
            flagged_for_review=True,
            failure_category="none",
            eval_notes="Eval scoring failed — JSON parse error.",
        )

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="eval_safety",
            step_type="model_response",
            error=f"JSON parse error: {str(e)}",
        ))

        return {
            **state,
            "eval_scores":        default_scores.model_dump(),
            "flagged_for_review": True,
            "failure_category":   "none",
            "errors":             [{"agent": "eval_safety", "error": str(e)}],
            "trace_steps":        trace_steps,
        }

    except Exception as e:
        logger.error("eval_safety_agent_failed", error=str(e))

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="eval_safety",
            step_type="model_response",
            error=str(e),
        ))

        return {
            **state,
            "flagged_for_review": True,
            "errors":             [{"agent": "eval_safety", "error": str(e)}],
            "trace_steps":        trace_steps,
        }


# ============================================================
# SUPABASE EVAL WRITER
# ============================================================

def _write_eval_results(
    conversation_id: str,
    eval_scores: EvalScores,
    model: str,
) -> None:
    """
    Writes eval scores to evals_eval_results in Supabase.
    """
    try:
        supabase = get_supabase()
        supabase.table("evals_eval_results").insert({
            "id":                       str(uuid.uuid4()),
            "conversation_id":          conversation_id,
            "model":                    model,
            "task_success":             eval_scores.task_success,
            "grounding_accuracy":       eval_scores.grounding_accuracy,
            "tool_correctness":         eval_scores.tool_correctness,
            "policy_compliance":        eval_scores.policy_compliance,
            "escalation_correctness":   eval_scores.escalation_correctness,
            "avg_latency_ms":           eval_scores.avg_latency_ms,
            "total_cost_usd":           eval_scores.total_cost_usd,
            "flagged_for_review":       eval_scores.flagged_for_review,
            "failure_category":         eval_scores.failure_category,
            "eval_notes":               eval_scores.eval_notes,
            "created_at":               datetime.now(timezone.utc).isoformat(),
        }).execute()
        logger.info("eval_results_written", conversation_id=conversation_id)
    except Exception as e:
        logger.error("eval_results_write_failed", error=str(e))