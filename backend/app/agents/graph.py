# ============================================================
# AgAI_31: LangGraph Orchestration Graph
# Wires all 6 agents into a single executable pipeline
# ============================================================

import uuid
import structlog
from langgraph.graph import StateGraph, END

from app.schemas.models import AgentState
from app.agents.router_agent import router_agent, route_by_intent
from app.agents.billing_agent import billing_agent
from app.agents.policy_agent import policy_agent
from app.agents.tool_executor_agent import tool_executor_agent
from app.agents.response_agent import response_agent
from app.agents.eval_safety_agent import eval_safety_agent
from app.observability.tracer import (
    create_conversation,
    update_conversation,
    flush_trace_steps,
)

logger = structlog.get_logger()


# ============================================================
# ROUTING HELPERS
# Used as conditional edge functions
# ============================================================

def route_after_billing(state: AgentState) -> str:
    """
    After billing agent: refund_request goes to policy then tool executor.
    billing_query goes straight to response.
    """
    intent = state.get("intent", "general")
    if intent == "refund_request":
        return "policy_agent"
    return "response_agent"


def route_after_policy(state: AgentState) -> str:
    """
    After policy agent: refund_request goes to tool executor.
    policy_check goes straight to response.
    """
    intent = state.get("intent", "general")
    if intent == "refund_request":
        return "tool_executor_agent"
    return "response_agent"


# ============================================================
# BUILD GRAPH
# ============================================================

def build_graph() -> StateGraph:
    """
    Constructs and compiles the LangGraph multi-agent graph.

    Flow:
    router -> [billing | policy | tool_executor | response] (by intent)
    billing -> [policy | response] (by intent)
    policy  -> [tool_executor | response] (by intent)
    tool_executor -> response
    response -> eval_safety -> END
    """
    graph = StateGraph(AgentState)

    # --------------------------------------------------------
    # Register nodes
    # --------------------------------------------------------
    graph.add_node("router_agent",          router_agent)
    graph.add_node("billing_agent",         billing_agent)
    graph.add_node("policy_agent",          policy_agent)
    graph.add_node("tool_executor_agent",   tool_executor_agent)
    graph.add_node("response_agent",        response_agent)
    graph.add_node("eval_safety_agent",     eval_safety_agent)

    # --------------------------------------------------------
    # Entry point
    # --------------------------------------------------------
    graph.set_entry_point("router_agent")

    # --------------------------------------------------------
    # Conditional edges from router
    # --------------------------------------------------------
    graph.add_conditional_edges(
        "router_agent",
        route_by_intent,
        {
            "billing_agent":        "billing_agent",
            "policy_agent":         "policy_agent",
            "tool_executor_agent":  "tool_executor_agent",
            "response_agent":       "response_agent",
        },
    )

    # --------------------------------------------------------
    # Conditional edges from billing
    # --------------------------------------------------------
    graph.add_conditional_edges(
        "billing_agent",
        route_after_billing,
        {
            "policy_agent":     "policy_agent",
            "response_agent":   "response_agent",
        },
    )

    # --------------------------------------------------------
    # Conditional edges from policy
    # --------------------------------------------------------
    graph.add_conditional_edges(
        "policy_agent",
        route_after_policy,
        {
            "tool_executor_agent":  "tool_executor_agent",
            "response_agent":       "response_agent",
        },
    )

    # --------------------------------------------------------
    # Linear edges: tool_executor -> response -> eval -> END
    # --------------------------------------------------------
    graph.add_edge("tool_executor_agent",   "response_agent")
    graph.add_edge("response_agent",        "eval_safety_agent")
    graph.add_edge("eval_safety_agent",     END)

    return graph.compile()


# ============================================================
# COMPILED GRAPH SINGLETON
# ============================================================

compiled_graph = build_graph()


# ============================================================
# GRAPH RUNNER
# Entry point called by the API layer
# ============================================================

def run_graph(
    user_message:   str,
    session_id:     str = None,
    customer_id:    str = "cust_001",
    primary_model:  str = "gpt-4o",
    fallback_model: str = "claude-3-5-sonnet-20241022",
) -> dict:
    """
    Runs the full multi-agent graph for a single conversation turn.

    1. Creates conversation record in Supabase
    2. Builds initial AgentState
    3. Invokes compiled LangGraph graph
    4. Flushes trace steps to Supabase
    5. Updates conversation with final outcome
    6. Returns structured result dict
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    # --------------------------------------------------------
    # Create conversation record
    # --------------------------------------------------------
    conversation_id = create_conversation(
        session_id=session_id,
        user_message=user_message,
    )

    logger.info(
        "graph_run_start",
        session_id=session_id,
        conversation_id=conversation_id,
    )

    # --------------------------------------------------------
    # Build initial state
    # --------------------------------------------------------
    initial_state: AgentState = {
        "session_id":       session_id,
        "conversation_id":  conversation_id,
        "turn_id":          1,
        "user_message":     user_message,
        "primary_model":    primary_model,
        "fallback_model":   fallback_model,
        "customer_profile": {"customer_id": customer_id},
        "total_tokens_in":  0,
        "total_tokens_out": 0,
        "total_cost_usd":   0.0,
        "total_latency_ms": 0,
        "trace_steps":      [],
        "errors":           [],
    }

    # --------------------------------------------------------
    # Run graph
    # --------------------------------------------------------
    try:
        final_state = compiled_graph.invoke(initial_state)

        # Flush all trace steps to Supabase
        flush_trace_steps(final_state.get("trace_steps", []))

        # Determine outcome
        outcome = "resolved"
        if final_state.get("pending_approval_ids"):
            outcome = "pending"
        elif final_state.get("flagged_for_review"):
            outcome = "flagged"
        elif final_state.get("errors"):
            outcome = "failed"

        # Update conversation record
        update_conversation(
            conversation_id=conversation_id,
            intent=final_state.get("intent"),
            outcome=outcome,
            total_cost_usd=final_state.get("total_cost_usd", 0.0),
            total_latency_ms=final_state.get("total_latency_ms", 0),
            total_tokens_in=final_state.get("total_tokens_in", 0),
            total_tokens_out=final_state.get("total_tokens_out", 0),
        )

        logger.info(
            "graph_run_complete",
            conversation_id=conversation_id,
            intent=final_state.get("intent"),
            outcome=outcome,
            cost_usd=final_state.get("total_cost_usd"),
        )

        return {
            "session_id":           session_id,
            "conversation_id":      conversation_id,
            "intent":               final_state.get("intent"),
            "response":             final_state.get("final_response"),
            "citations":            final_state.get("citations", []),
            "eval_scores":          final_state.get("eval_scores"),
            "flagged_for_review":   final_state.get("flagged_for_review", False),
            "failure_category":     final_state.get("failure_category"),
            "pending_approvals":    final_state.get("pending_approval_ids", []),
            "outcome":              outcome,
            "total_cost_usd":       final_state.get("total_cost_usd", 0.0),
            "total_latency_ms":     final_state.get("total_latency_ms", 0),
            "errors":               final_state.get("errors", []),
        }

    except Exception as e:
        logger.error("graph_run_failed", error=str(e), conversation_id=conversation_id)

        update_conversation(
            conversation_id=conversation_id,
            outcome="failed",
        )

        return {
            "session_id":       session_id,
            "conversation_id":  conversation_id,
            "intent":           None,
            "response":         "We encountered an error processing your request. Please try again.",
            "citations":        [],
            "eval_scores":      None,
            "flagged_for_review": True,
            "pending_approvals": [],
            "outcome":          "failed",
            "errors":           [{"agent": "graph", "error": str(e)}],
        }