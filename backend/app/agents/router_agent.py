# ============================================================
# AgAI_31: Router Agent
# Classifies user intent and sets routing decision
# ============================================================

import time
import structlog
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.models import AgentState
from app.tools.llm import invoke_with_fallback
from app.observability.tracer import build_trace_step

logger = structlog.get_logger()

# ============================================================
# INTENT CATEGORIES
# ============================================================

VALID_INTENTS = [
    "billing_query",
    "refund_request",
    "policy_check",
    "escalation",
    "general",
]

ROUTER_SYSTEM_PROMPT = """You are a customer support intent classifier for a billing and support platform.

Your job is to classify the user's message into exactly one of these intent categories:

- billing_query: Questions about invoices, charges, payment methods, account balance, subscription status
- refund_request: Requests to refund a charge, reverse a payment, or dispute a transaction
- policy_check: Questions about refund policy, terms of service, SLA, cancellation policy, or billing rules
- escalation: Requests to speak to a human, complaints requiring human judgment, threats, or legal mentions
- general: Anything that does not fit the above categories

Respond with ONLY the intent label. No explanation. No punctuation. Just the label.

Examples:
User: "I was charged twice this month" -> refund_request
User: "What is your refund policy?" -> policy_check
User: "I need to speak to a manager" -> escalation
User: "When is my next billing date?" -> billing_query
User: "How do I change my password?" -> general
"""


# ============================================================
# ROUTER AGENT NODE
# ============================================================

def router_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: classifies user intent and routes accordingly.
    Writes a routing_decision trace step to state.
    """
    conversation_id = state.get("conversation_id", "unknown")
    turn_id         = state.get("turn_id", 0)
    user_message    = state.get("user_message", "")

    logger.info("router_agent_start", conversation_id=conversation_id)

    messages = [
        SystemMessage(content=ROUTER_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    start = time.time()
    try:
        response, model_used, latency_ms, tokens_in, tokens_out, cost = invoke_with_fallback(
            messages=messages,
            temperature=0.0,
            context="router_agent",
        )

        raw_intent = response.content.strip().lower()

        # Validate intent — fall back to "general" if unrecognized
        intent = raw_intent if raw_intent in VALID_INTENTS else "general"

        if raw_intent not in VALID_INTENTS:
            logger.warning(
                "router_unknown_intent",
                raw=raw_intent,
                fallback="general",
            )

        logger.info(
            "router_agent_complete",
            intent=intent,
            model=model_used,
            latency_ms=latency_ms,
        )

        # Build trace step
        trace_step = build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="router",
            step_type="routing_decision",
            prompt_text=ROUTER_SYSTEM_PROMPT + f"\n\nUser: {user_message}",
            model_response=intent,
            latency_ms=latency_ms,
            token_count_input=tokens_in,
            token_count_output=tokens_out,
            cost_usd=cost,
        )

        return {
            **state,
            "intent":           intent,
            "primary_model":    model_used,
            "total_tokens_in":  state.get("total_tokens_in", 0) + tokens_in,
            "total_tokens_out": state.get("total_tokens_out", 0) + tokens_out,
            "total_cost_usd":   state.get("total_cost_usd", 0.0) + cost,
            "total_latency_ms": state.get("total_latency_ms", 0) + latency_ms,
            "trace_steps":      [trace_step],
        }

    except Exception as e:
        logger.error("router_agent_failed", error=str(e))

        error_trace = build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="router",
            step_type="routing_decision",
            error=str(e),
        )

        return {
            **state,
            "intent":       "general",
            "errors":       [{"agent": "router", "error": str(e)}],
            "trace_steps":  [error_trace],
        }


# ============================================================
# ROUTING FUNCTION
# Used as the conditional edge in the LangGraph graph
# ============================================================

def route_by_intent(state: AgentState) -> str:
    """
    Returns the next node name based on classified intent.
    Used as the conditional edge function in the graph.
    """
    intent = state.get("intent", "general")

    routing_map = {
        "billing_query":    "billing_agent",
        "refund_request":   "billing_agent",    # billing context needed before policy
        "policy_check":     "policy_agent",
        "escalation":       "tool_executor_agent",
        "general":          "response_agent",
    }

    next_node = routing_map.get(intent, "response_agent")
    logger.info("routing_to", intent=intent, next_node=next_node)
    return next_node