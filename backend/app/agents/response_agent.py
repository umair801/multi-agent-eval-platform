# ============================================================
# AgAI_31: Response Agent
# Synthesizes final grounded user-facing response
# ============================================================

import time
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.models import AgentState
from app.tools.llm import invoke_with_fallback
from app.observability.tracer import build_trace_step

logger = structlog.get_logger()

# ============================================================
# RESPONSE SYNTHESIS PROMPT
# ============================================================

RESPONSE_SYSTEM_PROMPT = """You are a customer support response agent for a billing platform.

Your job is to write the final response to the customer based ONLY on the context provided.

STRICT RULES:
1. You may ONLY use information from the billing context, policy excerpts, and tool results provided.
2. You may NOT introduce any information not present in the provided context.
3. If a refund ticket was created, confirm the ticket ID and ETA to the customer.
4. If a tool call is pending human approval, inform the customer their request is under review.
5. If an escalation was triggered, inform the customer a support agent will follow up.
6. Add citation references like [Source: refund_policy_v2.pdf] when quoting policy.
7. Be concise, empathetic, and professional.
8. Never say "I don't know" — if context is insufficient, say the team will follow up.

Response format:
- Address the customer's question directly in the first sentence
- Provide relevant details from billing context
- Cite any policy used
- State next steps clearly
"""


# ============================================================
# PENDING APPROVAL RESPONSE TEMPLATE
# ============================================================

PENDING_APPROVAL_TEMPLATE = """Thank you for reaching out. Your request has been received and is currently \
pending review by our support team.

A team member will review and action your request shortly. You will receive a confirmation \
once it has been processed.

If you have additional questions in the meantime, please don't hesitate to ask."""


# ============================================================
# RESPONSE AGENT NODE
# ============================================================

def response_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: synthesizes the final grounded response
    from billing context, policy excerpts, and tool results.
    """
    conversation_id  = state.get("conversation_id", "unknown")
    turn_id          = state.get("turn_id", 0)
    user_message     = state.get("user_message", "")
    intent           = state.get("intent", "general")
    billing_context  = state.get("billing_context") or "No billing context available."
    policy_excerpts  = state.get("policy_excerpts") or []
    grounding_sources= state.get("citations") or state.get("grounding_sources") or []
    policy_context   = state.get("policy_context") or ""
    tool_results     = state.get("tool_results") or []
    pending_approvals= state.get("pending_approval_ids") or []
    errors           = state.get("errors") or []

    logger.info("response_agent_start", conversation_id=conversation_id, intent=intent)

    trace_steps = []

    # --------------------------------------------------------
    # Fast path: pending approval
    # --------------------------------------------------------
    if pending_approvals:
        logger.info(
            "response_agent_pending_approval",
            conversation_id=conversation_id,
            approvals=pending_approvals,
        )

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="response",
            step_type="model_response",
            model_response=PENDING_APPROVAL_TEMPLATE,
        ))

        return {
            **state,
            "final_response":   PENDING_APPROVAL_TEMPLATE,
            "citations":        [],
            "trace_steps":      trace_steps,
        }

    # --------------------------------------------------------
    # Build synthesis context
    # --------------------------------------------------------
    tool_results_text = ""
    if tool_results:
        for tr in tool_results:
            tool_output = tr.get("tool_output", {})
            tool_name   = tr.get("tool_name", "unknown_tool")
            status      = tr.get("status", "")

            if status in ("auto_executed", "approved"):
                tool_results_text += f"\nTool: {tool_name}\nResult: {tool_output}\n"

    policy_text = ""
    if policy_context:
        policy_text = policy_context
    elif policy_excerpts:
        for excerpt in policy_excerpts[:3]:
            if excerpt.get("score", 0) >= 0.6:
                policy_text += (
                    f"\n[Source: {excerpt.get('source', 'policy')}] "
                    f"{excerpt.get('text', '')}\n"
                )

    synthesis_context = f"""User Question: {user_message}

Intent: {intent}

Billing Context:
{billing_context}

Policy Excerpts:
{policy_text if policy_text else 'No policy excerpts retrieved.'}

Tool Execution Results:
{tool_results_text if tool_results_text else 'No tools were executed.'}

Errors (if any):
{errors if errors else 'None'}

Write a grounded, empathetic response to the customer."""

    messages = [
        SystemMessage(content=RESPONSE_SYSTEM_PROMPT),
        HumanMessage(content=synthesis_context),
    ]

    start = time.time()
    try:
        response, model_used, latency_ms, tokens_in, tokens_out, cost = invoke_with_fallback(
            messages=messages,
            temperature=0.1,
            context="response_agent",
        )

        final_response = response.content.strip()

        # Extract citations from grounding sources
        citations = [
            src if isinstance(src, dict) else {"source": src, "type": "policy"}
            for src in grounding_sources
        ]

        # Add tool citations
        for tr in tool_results:
            if tr.get("status") in ("auto_executed", "approved"):
                citations.append({
                    "source": tr.get("tool_name"),
                    "type":   "tool_result",
                })

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="response",
            step_type="model_response",
            prompt_text=synthesis_context,
            model_response=final_response,
            latency_ms=latency_ms,
            token_count_input=tokens_in,
            token_count_output=tokens_out,
            cost_usd=cost,
        ))

        logger.info(
            "response_agent_complete",
            conversation_id=conversation_id,
            latency_ms=latency_ms,
            citations=len(citations),
        )

        return {
            **state,
            "final_response":   final_response,
            "citations":        citations,
            "total_tokens_in":  state.get("total_tokens_in", 0) + tokens_in,
            "total_tokens_out": state.get("total_tokens_out", 0) + tokens_out,
            "total_cost_usd":   state.get("total_cost_usd", 0.0) + cost,
            "total_latency_ms": state.get("total_latency_ms", 0) + latency_ms,
            "trace_steps":      trace_steps,
        }

    except Exception as e:
        logger.error("response_agent_failed", error=str(e))

        fallback_response = (
            "We encountered an issue processing your request. "
            "A support team member will follow up with you shortly."
        )

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="response",
            step_type="model_response",
            error=str(e),
        ))

        return {
            **state,
            "final_response":   fallback_response,
            "citations":        [],
            "errors":           [{"agent": "response", "error": str(e)}],
            "trace_steps":      trace_steps,
        }