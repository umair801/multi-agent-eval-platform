# ============================================================
# AgAI_31: Billing Agent
# Fetches customer profile and invoice history via Tool Gateway
# ============================================================

import time
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.models import AgentState, ToolCallRequest
from app.tools.llm import invoke_with_fallback
from app.observability.tracer import build_trace_step
from app.gateway.tool_gateway import gateway

logger = structlog.get_logger()

# ============================================================
# BILLING CONTEXT SYNTHESIS PROMPT
# ============================================================

BILLING_SYSTEM_PROMPT = """You are a billing context synthesizer for a customer support platform.

You will receive raw customer profile data and invoice history in JSON format.
Your job is to produce a clear, structured billing context summary that the Response Agent
can use to answer the customer's question.

Include:
- Customer name, plan, and account status
- Recent invoice history (highlight duplicates, overdue, or unpaid invoices)
- Any anomalies (duplicate charges, negative balance, suspended account)
- A one-line assessment of the billing situation

Be factual. Do not make recommendations. Do not address the customer directly.
Output plain text, no JSON, no markdown headers.
"""


# ============================================================
# BILLING AGENT NODE
# ============================================================

def billing_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: fetches billing data via Tool Gateway
    and synthesizes a billing context for the Response Agent.
    """
    conversation_id = state.get("conversation_id", "unknown")
    turn_id         = state.get("turn_id", 0)
    user_message    = state.get("user_message", "")
    intent          = state.get("intent", "billing_query")

    logger.info("billing_agent_start", conversation_id=conversation_id, intent=intent)

    # --------------------------------------------------------
    # Extract customer_id from state (set at API layer)
    # Default to cust_001 for demo purposes
    # --------------------------------------------------------
    customer_id = state.get("customer_profile", {})
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("customer_id", "cust_001")
    if not customer_id:
        customer_id = "cust_001"

    trace_steps     = []
    tool_results    = []
    total_latency   = 0
    total_cost      = 0.0
    total_tokens_in = 0
    total_tokens_out= 0

    # --------------------------------------------------------
    # Tool Call 1: get_customer_profile (LOW risk)
    # --------------------------------------------------------
    profile_request = ToolCallRequest(
        tool_name="get_customer_profile",
        tool_input={"customer_id": customer_id},
        risk_level="LOW",
        requested_by="billing_agent",
    )

    profile_result = gateway.process(profile_request, conversation_id)
    tool_results.append(profile_result.model_dump())

    trace_steps.append(build_trace_step(
        conversation_id=conversation_id,
        turn_id=turn_id,
        agent_name="billing",
        step_type="tool_call",
        tool_name="get_customer_profile",
        tool_input={"customer_id": customer_id},
        tool_output=profile_result.tool_output,
        latency_ms=profile_result.latency_ms or 0,
    ))

    customer_profile = profile_result.tool_output or {}

    # --------------------------------------------------------
    # Tool Call 2: get_invoice_history (LOW risk)
    # --------------------------------------------------------
    invoice_request = ToolCallRequest(
        tool_name="get_invoice_history",
        tool_input={"customer_id": customer_id, "limit": 10},
        risk_level="LOW",
        requested_by="billing_agent",
    )

    invoice_result = gateway.process(invoice_request, conversation_id)
    tool_results.append(invoice_result.model_dump())

    trace_steps.append(build_trace_step(
        conversation_id=conversation_id,
        turn_id=turn_id,
        agent_name="billing",
        step_type="tool_result",
        tool_name="get_invoice_history",
        tool_input={"customer_id": customer_id, "limit": 10},
        tool_output=invoice_result.tool_output,
        latency_ms=invoice_result.latency_ms or 0,
    ))

    invoice_history = invoice_result.tool_output or {}

    # --------------------------------------------------------
    # Synthesize billing context with LLM
    # --------------------------------------------------------
    synthesis_prompt = f"""Customer Profile:
{customer_profile}

Invoice History:
{invoice_history}

User Question: {user_message}

Produce a structured billing context summary."""

    messages = [
        SystemMessage(content=BILLING_SYSTEM_PROMPT),
        HumanMessage(content=synthesis_prompt),
    ]

    start = time.time()
    try:
        response, model_used, latency_ms, tokens_in, tokens_out, cost = invoke_with_fallback(
            messages=messages,
            temperature=0.0,
            context="billing_agent",
        )

        billing_context = response.content.strip()
        total_latency   += latency_ms
        total_cost      += cost
        total_tokens_in += tokens_in
        total_tokens_out+= tokens_out

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="billing",
            step_type="model_response",
            prompt_text=synthesis_prompt,
            model_response=billing_context,
            latency_ms=latency_ms,
            token_count_input=tokens_in,
            token_count_output=tokens_out,
            cost_usd=cost,
        ))

        logger.info(
            "billing_agent_complete",
            conversation_id=conversation_id,
            latency_ms=latency_ms,
        )

        return {
            **state,
            "customer_profile":     customer_profile,
            "invoice_history":      invoice_history.get("invoices", []),
            "billing_context":      billing_context,
            "tool_results":         (state.get("tool_results") or []) + tool_results,
            "total_tokens_in":      state.get("total_tokens_in", 0) + total_tokens_in,
            "total_tokens_out":     state.get("total_tokens_out", 0) + total_tokens_out,
            "total_cost_usd":       state.get("total_cost_usd", 0.0) + total_cost,
            "total_latency_ms":     state.get("total_latency_ms", 0) + total_latency,
            "trace_steps":          trace_steps,
        }

    except Exception as e:
        logger.error("billing_agent_failed", error=str(e))

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="billing",
            step_type="model_response",
            error=str(e),
        ))

        return {
            **state,
            "billing_context":  "Billing data unavailable due to an internal error.",
            "errors":           [{"agent": "billing", "error": str(e)}],
            "trace_steps":      trace_steps,
        }