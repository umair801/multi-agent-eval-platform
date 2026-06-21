# ============================================================
# AgAI_31: FastAPI Application — Main Entry Point
# ============================================================

import os
import uuid
import structlog
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.schemas.models import (
    ChatRequest,
    ChatResponse,
    MetricsResponse,
    ApprovalDecision,
)
from app.agents.graph import run_graph
from app.gateway.tool_gateway import gateway
from app.observability.tracer import get_supabase

load_dotenv()

logger = structlog.get_logger()

# ============================================================
# APP INIT
# ============================================================

app = FastAPI(
    title="Multi-Agent Eval Platform",
    description="Production multi-agent AI platform with eval framework, "
                "observability, and safe tool gateway. Built by Datawebify.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():
    return {
        "status":    "ok",
        "service":   "multi-agent-eval-platform",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# CHAT ENDPOINT
# Main entry point for conversation turns
# ============================================================

@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Submit a user message and run the full 6-agent pipeline.
    Returns the grounded response, intent, eval scores, and citations.
    """
    logger.info("chat_request", message=request.message[:80])

    result = run_graph(
        user_message=request.message,
        session_id=request.session_id or str(uuid.uuid4()),
        customer_id=request.customer_id or "cust_001",
    )

    return ChatResponse(
        session_id=         result["session_id"],
        response=           result["response"],
        intent=             result.get("intent"),
        citations=          result.get("citations", []),
        eval_scores=        result.get("eval_scores"),
        flagged=            result.get("flagged_for_review", False),
        pending_approvals=  result.get("pending_approvals", []),
    )


# ============================================================
# CONVERSATIONS
# ============================================================

@app.get("/api/v1/conversations")
def list_conversations(limit: int = 20, offset: int = 0):
    """
    List all conversations with summary metadata.
    """
    try:
        supabase = get_supabase()
        resp = supabase.table("evals_conversations")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .offset(offset)\
            .execute()
        return {"conversations": resp.data, "count": len(resp.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    """
    Get a single conversation with all trace steps.
    """
    try:
        supabase = get_supabase()

        conv = supabase.table("evals_conversations")\
            .select("*")\
            .eq("id", conversation_id)\
            .single()\
            .execute()

        steps = supabase.table("evals_trace_steps")\
            .select("*")\
            .eq("conversation_id", conversation_id)\
            .order("timestamp", desc=False)\
            .execute()

        evals = supabase.table("evals_eval_results")\
            .select("*")\
            .eq("conversation_id", conversation_id)\
            .execute()

        tool_calls = supabase.table("evals_tool_calls")\
            .select("*")\
            .eq("conversation_id", conversation_id)\
            .execute()

        return {
            "conversation":  conv.data,
            "trace_steps":   steps.data,
            "eval_results":  evals.data,
            "tool_calls":    tool_calls.data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CONVERSATION REPLAY
# ============================================================

@app.post("/api/v1/conversations/{conversation_id}/replay")
def replay_conversation(conversation_id: str):
    """
    Re-executes a saved conversation trace end-to-end.
    Useful for regression testing against new prompt or model versions.
    """
    try:
        supabase = get_supabase()

        conv = supabase.table("evals_conversations")\
            .select("*")\
            .eq("id", conversation_id)\
            .single()\
            .execute()

        original = conv.data
        if not original:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        result = run_graph(
            user_message=original["user_message"],
            session_id=str(uuid.uuid4()),
            customer_id="cust_001",
        )

        return {
            "original_conversation_id": conversation_id,
            "replay_conversation_id":   result["conversation_id"],
            "original_intent":          original.get("intent"),
            "replayed_intent":          result.get("intent"),
            "original_outcome":         original.get("outcome"),
            "replayed_outcome":         result.get("outcome"),
            "response":                 result.get("response"),
            "eval_scores":              result.get("eval_scores"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# HUMAN APPROVAL QUEUE
# ============================================================

@app.get("/api/v1/approvals")
def list_pending_approvals():
    """
    List all pending HIGH risk tool calls awaiting human approval.
    """
    try:
        supabase = get_supabase()
        resp = supabase.table("evals_approval_queue")\
            .select("*")\
            .eq("status", "pending")\
            .order("created_at", desc=True)\
            .execute()
        return {"pending_approvals": resp.data, "count": len(resp.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/approvals/{approval_id}/approve")
def approve_tool_call(approval_id: str, reviewed_by: str = "human"):
    """
    Approve a pending HIGH risk tool call and execute it.
    """
    try:
        result = gateway.approve_and_execute(
            approval_id=approval_id,
            reviewed_by=reviewed_by,
        )
        return {
            "approval_id":  approval_id,
            "status":       "approved",
            "tool_result":  result.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/approvals/{approval_id}/reject")
def reject_tool_call(
    approval_id:        str,
    rejection_reason:   str = "Rejected by reviewer.",
    reviewed_by:        str = "human",
):
    """
    Reject a pending HIGH risk tool call.
    """
    try:
        gateway.reject_tool_call(
            approval_id=approval_id,
            rejection_reason=rejection_reason,
            reviewed_by=reviewed_by,
        )
        return {
            "approval_id":      approval_id,
            "status":           "rejected",
            "rejection_reason": rejection_reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# METRICS ENDPOINT
# ============================================================

@app.get("/api/v1/metrics", response_model=MetricsResponse)
def get_metrics():
    """
    Returns platform-wide performance metrics.
    """
    try:
        supabase = get_supabase()

        convs = supabase.table("evals_conversations")\
            .select("total_latency_ms, total_cost_usd, outcome")\
            .execute()

        tool_calls = supabase.table("evals_tool_calls")\
            .select("status, risk_level")\
            .execute()

        evals = supabase.table("evals_eval_results")\
            .select("task_success, flagged_for_review")\
            .execute()

        conv_data   = convs.data or []
        tool_data   = tool_calls.data or []
        eval_data   = evals.data or []

        total_convs = len(conv_data)

        avg_latency = (
            sum(c.get("total_latency_ms", 0) for c in conv_data) / total_convs
            if total_convs else 0.0
        )
        avg_cost = (
            sum(c.get("total_cost_usd", 0) for c in conv_data) / total_convs
            if total_convs else 0.0
        )

        total_tools     = len(tool_data)
        approved_tools  = sum(1 for t in tool_data if t.get("status") in ("approved", "auto_executed"))
        approval_rate   = approved_tools / total_tools if total_tools else 0.0

        escalations     = sum(1 for c in conv_data if c.get("outcome") == "escalated")
        escalation_rate = escalations / total_convs if total_convs else 0.0

        task_success_rate = (
            sum(e.get("task_success", 0) for e in eval_data) / len(eval_data)
            if eval_data else 0.0
        )

        flagged = sum(1 for e in eval_data if e.get("flagged_for_review"))

        return MetricsResponse(
            avg_latency_ms=         round(avg_latency, 2),
            avg_cost_per_turn_usd=  round(avg_cost, 6),
            task_success_rate=      round(task_success_rate, 3),
            tool_approval_rate=     round(approval_rate, 3),
            escalation_rate=        round(escalation_rate, 3),
            total_conversations=    total_convs,
            total_tool_calls=       total_tools,
            flagged_conversations=  flagged,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# FAILURE DASHBOARD
# ============================================================

@app.get("/api/v1/failures")
def get_failure_dashboard():
    """
    Returns failure category breakdown and top failing intents.
    Used by the frontend failure dashboard pie chart.
    """
    try:
        supabase = get_supabase()

        evals = supabase.table("evals_eval_results")\
            .select("failure_category, flagged_for_review")\
            .execute()

        convs = supabase.table("evals_conversations")\
            .select("intent, outcome")\
            .eq("outcome", "failed")\
            .execute()

        eval_data   = evals.data or []
        conv_data   = convs.data or []

        # Failure category breakdown
        category_counts: dict = {}
        for e in eval_data:
            cat = e.get("failure_category") or "none"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Top failing intents
        intent_counts: dict = {}
        for c in conv_data:
            intent = c.get("intent") or "unknown"
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        return {
            "failure_categories":   category_counts,
            "top_failing_intents":  intent_counts,
            "total_flagged":        sum(1 for e in eval_data if e.get("flagged_for_review")),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# TRACE STEPS
# ============================================================

@app.get("/api/v1/traces/{conversation_id}")
def get_trace(conversation_id: str):
    """
    Returns all trace steps for a conversation, ordered by timestamp.
    """
    try:
        supabase = get_supabase()
        steps = supabase.table("evals_trace_steps")\
            .select("*")\
            .eq("conversation_id", conversation_id)\
            .order("timestamp", desc=False)\
            .execute()
        return {"trace_steps": steps.data, "count": len(steps.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/v1/conversations/{conversation_id}/trace")
def get_conversation_trace_alias(conversation_id: str):
    """
    Alias used by the frontend trace viewer.
    Returns conversation record + trace steps in the format the UI expects.
    """
    try:
        supabase = get_supabase()

        conv = supabase.table("evals_conversations")\
            .select("*")\
            .eq("id", conversation_id)\
            .single()\
            .execute()

        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")

        steps = supabase.table("evals_trace_steps")\
            .select("*")\
            .eq("conversation_id", conversation_id)\
            .order("timestamp", desc=False)\
            .execute()

        return {
            "conversation": conv.data,
            "steps": steps.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))