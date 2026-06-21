# ============================================================
# AgAI_31: Tool Executor Agent
# Handles HIGH risk tool calls: create_refund_ticket, escalate_to_human
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
# TOOL DECISION PROMPT
# ============================================================

TOOL_EXECUTOR_SYSTEM_PROMPT = """You are a tool execution decision agent for a customer support platform.

Based on the user message, intent, and billing context provided, decide which tool to call
and extract the required parameters.

Available tools:
1. create_refund_ticket — Use when a refund is clearly warranted based on billing context
   Required params: customer_id (str), amount (float), reason (str, min 10 chars)

2. escalate_to_human — Use when the issue requires human judgment, is a complaint,
   involves legal threats, or cannot be resolved automatically
   Required params: customer_id (str), reason (str, min 10 chars), priority (low|medium|high|critical)

3. none — Use when no tool call is needed

Respond in this exact format:
TOOL: [tool_name or none]
PARAMS: [JSON object with params, or {}]
REASONING: [one sentence explaining the decision]

Example:
TOOL: create_refund_ticket
PARAMS: {"customer_id": "cust_001", "amount": 99.00, "reason": "Duplicate charge detected on invoice inv_004"}
REASONING: Customer was charged twice in January 2025 for the same billing period.
"""


# ============================================================
# RESPONSE PARSER
# ============================================================

def _parse_tool_decision(response_text: str) -> tuple[str, dict, str]:
    """
    Parses the LLM tool decision response.
    Returns (tool_name, params_dict, reasoning).
    """
    import json
    import re

    tool_name = "none"
    params    = {}
    reasoning = ""

    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("TOOL:"):
            tool_name = line.replace("TOOL:", "").strip().lower()
        elif line.startswith("PARAMS:"):
            params_str = line.replace("PARAMS:", "").strip()
            try:
                params = json.loads(params_str)
            except Exception:
                # Try extracting JSON with regex
                match = re.search(r'\{.*\}', params_str)
                if match:
                    try:
                        params = json.loads(match.group())
                    except Exception:
                        params = {}
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return tool_name, params, reasoning


# ============================================================
# TOOL EXECUTOR AGENT NODE
# ============================================================

def tool_executor_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: decides which HIGH risk tool to call
    and submits it to the Tool Gateway.
    """
    conversation_id = state.get("conversation_id", "unknown")
    turn_id         = state.get("turn_id", 0)
    user_message    = state.get("user_message", "")
    intent          = state.get("intent", "general")
    billing_context = state.get("billing_context", "No billing context available.")
    customer_profile= state.get("customer_profile", {})

    logger.info("tool_executor_agent_start", conversation_id=conversation_id, intent=intent)

    trace_steps      = []
    pending_approvals= state.get("pending_approval_ids") or []
    tool_results     = state.get("tool_results") or []

    # --------------------------------------------------------
    # Step 1: LLM decides which tool to call
    # --------------------------------------------------------
    decision_prompt = f"""User Message: {user_message}

Intent: {intent}

Billing Context:
{billing_context}

Customer ID: {customer_profile.get('customer_id', 'unknown') if isinstance(customer_profile, dict) else 'unknown'}

Decide which tool to call."""

    messages = [
        SystemMessage(content=TOOL_EXECUTOR_SYSTEM_PROMPT),
        HumanMessage(content=decision_prompt),
    ]

    start = time.time()
    try:
        response, model_used, latency_ms, tokens_in, tokens_out, cost = invoke_with_fallback(
            messages=messages,
            temperature=0.0,
            context="tool_executor_agent",
        )

        tool_name, params, reasoning = _parse_tool_decision(response.content)

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="tool_executor",
            step_type="model_response",
            prompt_text=decision_prompt,
            model_response=response.content,
            latency_ms=latency_ms,
            token_count_input=tokens_in,
            token_count_output=tokens_out,
            cost_usd=cost,
        ))

        updated_state = {
            **state,
            "total_tokens_in":  state.get("total_tokens_in", 0) + tokens_in,
            "total_tokens_out": state.get("total_tokens_out", 0) + tokens_out,
            "total_cost_usd":   state.get("total_cost_usd", 0.0) + cost,
            "total_latency_ms": state.get("total_latency_ms", 0) + latency_ms,
        }

        logger.info(
            "tool_executor_decision",
            tool=tool_name,
            reasoning=reasoning,
            conversation_id=conversation_id,
        )

        # --------------------------------------------------------
        # Step 2: No tool needed
        # --------------------------------------------------------
        if tool_name == "none" or tool_name not in ["create_refund_ticket", "escalate_to_human"]:
            trace_steps.append(build_trace_step(
                conversation_id=conversation_id,
                turn_id=turn_id,
                agent_name="tool_executor",
                step_type="routing_decision",
                model_response="No tool call required.",
            ))
            return {
                **updated_state,
                "trace_steps": trace_steps,
            }

        # --------------------------------------------------------
        # Step 3: Submit tool call to gateway
        # --------------------------------------------------------
        customer_id = (
            customer_profile.get("customer_id", "cust_001")
            if isinstance(customer_profile, dict)
            else "cust_001"
        )

        # Ensure customer_id is in params
        if "customer_id" not in params:
            params["customer_id"] = customer_id

        tool_request = ToolCallRequest(
            tool_name=tool_name,
            tool_input=params,
            risk_level="HIGH",
            requested_by="tool_executor_agent",
        )

        tool_result = gateway.process(tool_request, conversation_id)
        tool_results.append(tool_result.model_dump())

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="tool_executor",
            step_type="tool_call",
            tool_name=tool_name,
            tool_input=params,
            tool_output=tool_result.tool_output,
            latency_ms=tool_result.latency_ms or 0,
        ))

        # --------------------------------------------------------
        # Step 4: Handle pending approval
        # --------------------------------------------------------
        if tool_result.status == "pending_approval":
            approval_id = (tool_result.tool_output or {}).get("approval_id")
            if approval_id:
                pending_approvals.append(approval_id)

            logger.info(
                "tool_queued_awaiting_approval",
                tool=tool_name,
                approval_id=approval_id,
                conversation_id=conversation_id,
            )

            return {
                **updated_state,
                "tool_results":         tool_results,
                "pending_approval_ids": pending_approvals,
                "trace_steps":          trace_steps,
            }

        # --------------------------------------------------------
        # Step 5: Tool executed (approved or auto-executed)
        # --------------------------------------------------------
        logger.info(
            "tool_executor_agent_complete",
            tool=tool_name,
            status=tool_result.status,
            conversation_id=conversation_id,
        )

        return {
            **updated_state,
            "tool_results":         tool_results,
            "pending_approval_ids": pending_approvals,
            "trace_steps":          trace_steps,
        }

    except Exception as e:
        logger.error("tool_executor_agent_failed", error=str(e))

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="tool_executor",
            step_type="tool_call",
            error=str(e),
        ))

        return {
            **state,
            "errors":       [{"agent": "tool_executor", "error": str(e)}],
            "trace_steps":  trace_steps,
        }