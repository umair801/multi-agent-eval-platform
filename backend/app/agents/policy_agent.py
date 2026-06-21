# ============================================================
# AgAI_31: Policy/Grounding Agent — Real RAG via Pinecone
# ============================================================

import os
import time
import structlog
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger()


def policy_agent(state: dict) -> dict:
    """
    Queries the Pinecone RAG knowledge base for relevant policy content.
    Returns grounded policy excerpts with source citations.
    Logs retrieval context to the trace store via build_trace_step.
    """
    from app.rag.retriever import retrieve_policy_context
    from app.observability.tracer import build_trace_step

    conversation_id = state.get("conversation_id", "unknown")
    turn_id = state.get("turn_id", 1)
    user_message = state.get("user_message", "")
    intent = state.get("intent", "general")
    trace_steps = list(state.get("trace_steps", []))
    errors = list(state.get("errors", []))

    # Build a targeted query combining user message + intent signal
    intent_hints = {
        "refund_request":   "refund policy eligibility process",
        "policy_check":     "terms of service billing policy",
        "duplicate_charge": "duplicate charge dispute refund policy",
        "billing_query":    "billing invoice payment policy",
        "escalation":       "escalation process SLA support",
        "general":          "general support policy",
    }
    hint = intent_hints.get(intent, "")
    query = f"{user_message} {hint}".strip()

    start = time.perf_counter()

    try:
        retrieval = retrieve_policy_context(query=query, top_k=5, token_budget=1500)
        latency_ms = (time.perf_counter() - start) * 1000

        context_text = retrieval["context_text"]
        citations = retrieval["citations"]

        # Append trace step to state (flushed to Supabase at end of turn)
        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="policy_agent",
            step_type="tool_call",
            tool_name="rag_retrieve",
            tool_input={
                "query": query,
                "top_k": 5,
                "token_budget": 1500,
            },
            tool_output={
                "chunks_retrieved": retrieval["chunks_retrieved"],
                "chunks_included":  retrieval["chunks_included"],
                "chunks_excluded":  retrieval["chunks_excluded"],
                "tokens_used":      retrieval["tokens_used"],
                "citations":        citations,
                "context_preview":  context_text[:300],
            },
            latency_ms=int(latency_ms),
        ))

        logger.info(
            "policy_agent_retrieved",
            conversation_id=conversation_id,
            citations=citations,
            tokens_used=retrieval["tokens_used"],
            chunks_included=retrieval["chunks_included"],
        )

        return {
            **state,
            "policy_context": context_text,
            "citations":      citations,
            "trace_steps":    trace_steps,
            "errors":         errors,
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error("policy_agent_error", error=str(e), conversation_id=conversation_id)
        errors.append({"agent": "policy_agent", "error": str(e)})

        trace_steps.append(build_trace_step(
            conversation_id=conversation_id,
            turn_id=turn_id,
            agent_name="policy_agent",
            step_type="tool_call",
            tool_name="rag_retrieve",
            tool_input={"query": query},
            error=str(e),
            latency_ms=int(latency_ms),
        ))

        return {
            **state,
            "policy_context": "",
            "citations":      [],
            "trace_steps":    trace_steps,
            "errors":         errors,
        }