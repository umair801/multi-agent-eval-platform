# ============================================================
# AgAI_31: RAG Retriever — Pinecone query + token budget
# ============================================================

import os
import structlog
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger()

NAMESPACE = "agai31-policy-kb"
TOP_K = 5
TOKEN_BUDGET = 1500         # max tokens of context per query
CHARS_PER_TOKEN = 4         # approximation


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def retrieve_policy_context(
    query: str,
    top_k: int = TOP_K,
    token_budget: int = TOKEN_BUDGET,
    score_threshold: float = 0.30,
) -> dict:
    """
    Query Pinecone for the top-k most relevant policy chunks.
    Applies a token budget: includes chunks until budget is exhausted.
    Returns:
        {
            "context_text": str,          # combined text within token budget
            "citations": list[str],        # source document names used
            "chunks_retrieved": int,
            "chunks_included": int,
            "chunks_excluded": int,
            "tokens_used": int,
            "token_budget": int,
        }
    """
    from pinecone import Pinecone
    from app.rag.embedder import get_embedding

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.environ["PINECONE_INDEX_NAME"])

    # Embed the query
    query_embedding = get_embedding(query)

    # Query Pinecone
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=NAMESPACE,
        include_metadata=True,
    )

    matches = results.get("matches", [])
    logger.info("pinecone_query", query_preview=query[:80], matches_found=len(matches))

    # Filter by score threshold and apply token budget
    included_chunks = []
    excluded_chunks = []
    tokens_used = 0
    citations = set()

    for match in matches:
        score = match.get("score", 0.0)
        metadata = match.get("metadata", {})
        chunk_text = metadata.get("text", "")
        source = metadata.get("source", "unknown")

        if score < score_threshold:
            excluded_chunks.append({"source": source, "reason": "below_threshold", "score": score})
            continue

        chunk_tokens = _estimate_tokens(chunk_text)

        if tokens_used + chunk_tokens > token_budget:
            # Try to fit a trimmed version
            remaining = token_budget - tokens_used
            if remaining < 50:  # not worth including a tiny fragment
                excluded_chunks.append({"source": source, "reason": "budget_exhausted", "score": score})
                continue
            # Trim to remaining budget
            trim_chars = remaining * CHARS_PER_TOKEN
            chunk_text = chunk_text[:trim_chars] + "..."
            chunk_tokens = remaining

        included_chunks.append({
            "text": chunk_text,
            "source": source,
            "score": round(score, 4),
            "tokens": chunk_tokens,
        })
        citations.add(source)
        tokens_used += chunk_tokens

        if tokens_used >= token_budget:
            break

    # Build combined context text
    context_parts = []
    for chunk in included_chunks:
        context_parts.append(f"[Source: {chunk['source']}]\n{chunk['text']}")
    context_text = "\n\n---\n\n".join(context_parts)

    logger.info(
        "retrieval_complete",
        chunks_retrieved=len(matches),
        chunks_included=len(included_chunks),
        chunks_excluded=len(excluded_chunks),
        tokens_used=tokens_used,
        citations=list(citations),
    )

    return {
        "context_text": context_text,
        "citations": sorted(list(citations)),
        "chunks_retrieved": len(matches),
        "chunks_included": len(included_chunks),
        "chunks_excluded": len(excluded_chunks),
        "tokens_used": tokens_used,
        "token_budget": token_budget,
        "included_chunks": included_chunks,
        "excluded_chunks": excluded_chunks,
    }