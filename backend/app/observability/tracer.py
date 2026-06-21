# ============================================================
# AgAI_31: Trace Writer — logs every agent step to Supabase
# ============================================================

import os
import uuid
import structlog
from datetime import datetime, timezone
from typing import Optional, Any

from supabase import create_client, Client
from dotenv import load_dotenv

from app.schemas.models import TraceStep

load_dotenv()

logger = structlog.get_logger()

# ============================================================
# SUPABASE CLIENT
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def create_conversation(
    session_id: str,
    user_message: str,
) -> str:
    """
    Creates a new conversation record in evals_conversations.
    Returns the conversation_id (UUID string).
    """
    supabase = get_supabase()
    conversation_id = str(uuid.uuid4())

    data = {
        "id":           conversation_id,
        "session_id":   session_id,
        "user_message": user_message,
        "outcome":      "pending",
        "turn_count":   1,
    }

    try:
        supabase.table("evals_conversations").insert(data).execute()
        logger.info("conversation_created", conversation_id=conversation_id, session_id=session_id)
    except Exception as e:
        logger.error("conversation_create_failed", error=str(e))
        raise

    return conversation_id


def update_conversation(
    conversation_id: str,
    intent:          Optional[str] = None,
    outcome:         Optional[str] = None,
    total_cost_usd:  Optional[float] = None,
    total_latency_ms: Optional[int] = None,
    total_tokens_in: Optional[int] = None,
    total_tokens_out: Optional[int] = None,
) -> None:
    """
    Updates conversation-level aggregates after each turn completes.
    """
    supabase = get_supabase()

    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if intent           is not None: updates["intent"]            = intent
    if outcome          is not None: updates["outcome"]           = outcome
    if total_cost_usd   is not None: updates["total_cost_usd"]    = total_cost_usd
    if total_latency_ms is not None: updates["total_latency_ms"]  = total_latency_ms
    if total_tokens_in  is not None: updates["total_tokens_in"]   = total_tokens_in
    if total_tokens_out is not None: updates["total_tokens_out"]  = total_tokens_out

    try:
        supabase.table("evals_conversations").update(updates).eq("id", conversation_id).execute()
        logger.info("conversation_updated", conversation_id=conversation_id)
    except Exception as e:
        logger.error("conversation_update_failed", error=str(e))


# ============================================================
# TRACE STEP WRITER
# ============================================================

def write_trace_step(step: TraceStep) -> None:
    """
    Writes a single trace step to evals_trace_steps.
    Called by every agent after each operation.
    """
    supabase = get_supabase()

    data = {
        "id":                   str(uuid.uuid4()),
        "conversation_id":      step.conversation_id,
        "turn_id":              step.turn_id,
        "agent_name":           step.agent_name,
        "step_type":            step.step_type,
        "prompt_text":          step.prompt_text,
        "model_response":       step.model_response,
        "tool_name":            step.tool_name,
        "tool_input":           step.tool_input,
        "tool_output":          step.tool_output if isinstance(step.tool_output, dict) else
                                {"result": str(step.tool_output)} if step.tool_output else None,
        "latency_ms":           step.latency_ms,
        "token_count_input":    step.token_count_input,
        "token_count_output":   step.token_count_output,
        "cost_usd":             step.cost_usd,
        "error":                step.error,
        "timestamp":            step.timestamp.isoformat(),
    }

    try:
        supabase.table("evals_trace_steps").insert(data).execute()
        logger.info(
            "trace_step_written",
            conversation_id=step.conversation_id,
            agent=step.agent_name,
            step_type=step.step_type,
        )
    except Exception as e:
        logger.error("trace_step_write_failed", error=str(e), agent=step.agent_name)


# ============================================================
# BULK TRACE WRITER
# Writes all trace steps accumulated in state at end of turn
# ============================================================

def flush_trace_steps(trace_steps: list[dict]) -> None:
    """
    Writes all accumulated trace steps from LangGraph state to Supabase.
    Called once at the end of each conversation turn.
    """
    if not trace_steps:
        return

    supabase = get_supabase()
    rows = []

    for step in trace_steps:
        rows.append({
            "id":                   str(uuid.uuid4()),
            "conversation_id":      step.get("conversation_id"),
            "turn_id":              step.get("turn_id", 0),
            "agent_name":           step.get("agent_name"),
            "step_type":            step.get("step_type"),
            "prompt_text":          step.get("prompt_text"),
            "model_response":       step.get("model_response"),
            "tool_name":            step.get("tool_name"),
            "tool_input":           step.get("tool_input"),
            "tool_output":          step.get("tool_output"),
            "latency_ms":           step.get("latency_ms"),
            "token_count_input":    step.get("token_count_input"),
            "token_count_output":   step.get("token_count_output"),
            "cost_usd":             step.get("cost_usd"),
            "error":                step.get("error"),
            "timestamp":            step.get("timestamp", datetime.now(timezone.utc).isoformat()),
        })

    try:
        supabase.table("evals_trace_steps").insert(rows).execute()
        logger.info("trace_steps_flushed", count=len(rows))
    except Exception as e:
        logger.error("trace_steps_flush_failed", error=str(e), count=len(rows))


# ============================================================
# HELPER: Build a trace step dict for state accumulation
# Agents append this to state["trace_steps"] during execution
# ============================================================

def build_trace_step(
    conversation_id:    str,
    turn_id:            int,
    agent_name:         str,
    step_type:          str,
    prompt_text:        Optional[str] = None,
    model_response:     Optional[str] = None,
    tool_name:          Optional[str] = None,
    tool_input:         Optional[dict] = None,
    tool_output:        Optional[Any] = None,
    latency_ms:         Optional[int] = None,
    token_count_input:  Optional[int] = None,
    token_count_output: Optional[int] = None,
    cost_usd:           Optional[float] = None,
    error:              Optional[str] = None,
) -> dict:
    """
    Returns a trace step dict ready to be appended to state['trace_steps'].
    """
    return {
        "conversation_id":      conversation_id,
        "turn_id":              turn_id,
        "agent_name":           agent_name,
        "step_type":            step_type,
        "prompt_text":          prompt_text,
        "model_response":       model_response,
        "tool_name":            tool_name,
        "tool_input":           tool_input,
        "tool_output":          tool_output if isinstance(tool_output, dict)
                                else {"result": str(tool_output)} if tool_output else None,
        "latency_ms":           latency_ms,
        "token_count_input":    token_count_input,
        "token_count_output":   token_count_output,
        "cost_usd":             cost_usd,
        "error":                error,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
    }