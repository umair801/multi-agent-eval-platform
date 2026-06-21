# ============================================================
# AgAI_31: LLM Client Factory with GPT-4o Primary + Claude Fallback
# ============================================================

import os
import time
import structlog
from typing import Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

load_dotenv()

logger = structlog.get_logger()

# ============================================================
# CONFIG
# ============================================================

PRIMARY_MODEL   = os.getenv("PRIMARY_MODEL", "gpt-4o")
FALLBACK_MODEL  = os.getenv("FALLBACK_MODEL", "claude-3-5-sonnet-20241022")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# ============================================================
# CLIENT FACTORY
# ============================================================

def get_primary_llm(temperature: float = 0.0) -> ChatOpenAI:
    """
    Returns a GPT-4o LangChain client.
    temperature=0.0 by default for deterministic agent outputs.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in environment.")

    return ChatOpenAI(
        model=PRIMARY_MODEL,
        temperature=temperature,
        api_key=OPENAI_API_KEY,
        max_retries=2,
        request_timeout=60,
    )


def get_fallback_llm(temperature: float = 0.0) -> ChatAnthropic:
    """
    Returns a Claude LangChain client used as fallback.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set in environment.")

    return ChatAnthropic(
        model=FALLBACK_MODEL,
        temperature=temperature,
        api_key=ANTHROPIC_API_KEY,
        max_retries=2,
        timeout=60,
    )


# ============================================================
# INVOKE WITH FALLBACK
# Tries primary (GPT-4o), falls back to Claude on failure.
# Returns: (response, model_used, latency_ms, tokens_in, tokens_out, cost_usd)
# ============================================================

def invoke_with_fallback(
    messages: list,
    temperature: float = 0.0,
    context: str = "unknown_agent",
) -> tuple[BaseMessage, str, int, int, int, float]:
    """
    Invoke the primary LLM. On any exception, fall back to Claude.

    Returns a tuple:
        (response, model_used, latency_ms, tokens_in, tokens_out, cost_usd)
    """
    primary = get_primary_llm(temperature)

    start = time.time()
    try:
        response = primary.invoke(messages)
        latency_ms = int((time.time() - start) * 1000)
        tokens_in, tokens_out, cost = _extract_usage(response, model=PRIMARY_MODEL)

        logger.info(
            "llm_primary_success",
            agent=context,
            model=PRIMARY_MODEL,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return response, PRIMARY_MODEL, latency_ms, tokens_in, tokens_out, cost

    except Exception as primary_error:
        logger.warning(
            "llm_primary_failed_falling_back",
            agent=context,
            error=str(primary_error),
            fallback_model=FALLBACK_MODEL,
        )

    # Fallback
    fallback = get_fallback_llm(temperature)
    start = time.time()
    try:
        response = fallback.invoke(messages)
        latency_ms = int((time.time() - start) * 1000)
        tokens_in, tokens_out, cost = _extract_usage(response, model=FALLBACK_MODEL)

        logger.info(
            "llm_fallback_success",
            agent=context,
            model=FALLBACK_MODEL,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return response, FALLBACK_MODEL, latency_ms, tokens_in, tokens_out, cost

    except Exception as fallback_error:
        logger.error(
            "llm_fallback_failed",
            agent=context,
            error=str(fallback_error),
        )
        raise RuntimeError(
            f"Both primary ({PRIMARY_MODEL}) and fallback ({FALLBACK_MODEL}) failed. "
            f"Last error: {fallback_error}"
        )


# ============================================================
# USAGE EXTRACTION
# Pulls token counts and estimates cost from the LLM response.
# ============================================================

# Cost per 1000 tokens (USD) — update as pricing changes
COST_PER_1K = {
    "gpt-4o":                       {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":                  {"input": 0.00015,"output": 0.0006},
    "claude-3-5-sonnet-20241022":   {"input": 0.003,  "output": 0.015},
    "claude-3-haiku-20240307":      {"input": 0.00025,"output": 0.00125},
}


def _extract_usage(
    response: BaseMessage,
    model: str,
) -> tuple[int, int, float]:
    """
    Extract token counts and compute cost from a LangChain response.
    Returns (tokens_in, tokens_out, cost_usd).
    """
    tokens_in = 0
    tokens_out = 0

    usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {})

    if isinstance(usage, dict):
        tokens_in  = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        tokens_out = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    elif hasattr(usage, "input_tokens"):
        tokens_in  = usage.input_tokens or 0
        tokens_out = usage.output_tokens or 0

    rates = COST_PER_1K.get(model, {"input": 0.005, "output": 0.015})
    cost_usd = (tokens_in / 1000 * rates["input"]) + (tokens_out / 1000 * rates["output"])

    return tokens_in, tokens_out, round(cost_usd, 6)