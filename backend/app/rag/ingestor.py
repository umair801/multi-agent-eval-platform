# ============================================================
# AgAI_31: RAG Ingestor — Chunk + Embed + Upsert to Pinecone
# ============================================================

import os
import uuid
import json
from pathlib import Path
from typing import Optional
import structlog
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger()

NAMESPACE = "agai31-policy-kb"
CHUNK_SIZE = 400        # tokens approx (chars / 4)
CHUNK_OVERLAP = 80


# ============================================================
# TEXT CHUNKER
# ============================================================

def chunk_text(text: str, source_name: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Split text into overlapping chunks.
    Returns list of dicts with: chunk_id, text, source, char_start, char_end.
    """
    words = text.split()
    # Approximate: chunk_size chars ~ chunk_size/5 words
    words_per_chunk = max(1, chunk_size // 5)
    overlap_words = max(0, overlap // 5)

    chunks = []
    i = 0
    chunk_index = 0

    while i < len(words):
        chunk_words = words[i: i + words_per_chunk]
        chunk_text_str = " ".join(chunk_words)

        chunks.append({
            "chunk_id": f"{source_name}_chunk_{chunk_index:04d}",
            "text": chunk_text_str,
            "source": source_name,
            "chunk_index": chunk_index,
            "word_start": i,
            "word_end": i + len(chunk_words),
            "char_count": len(chunk_text_str),
        })

        chunk_index += 1
        i += words_per_chunk - overlap_words

    logger.info("chunked", source=source_name, total_chunks=len(chunks))
    return chunks


# ============================================================
# PLAIN TEXT LOADER
# ============================================================

def load_text_file(file_path: Path) -> str:
    """Load a .txt file and return its content."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# PINECONE UPSERT
# ============================================================

def upsert_chunks_to_pinecone(chunks: list[dict], embeddings: list[list[float]]) -> int:
    """
    Upsert chunk vectors to Pinecone.
    Returns number of vectors upserted.
    """
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.environ["PINECONE_INDEX_NAME"])

    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        vectors.append({
            "id": chunk["chunk_id"],
            "values": embedding,
            "metadata": {
                "text": chunk["text"],
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
                "char_count": chunk["char_count"],
            },
        })

    # Upsert in batches of 100
    batch_size = 100
    total_upserted = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i: i + batch_size]
        index.upsert(vectors=batch, namespace=NAMESPACE)
        total_upserted += len(batch)
        logger.info("upserted_batch", batch_start=i, count=len(batch))

    return total_upserted


# ============================================================
# MAIN INGEST FUNCTION
# ============================================================

def ingest_documents(docs_dir: Optional[str] = None) -> dict:
    """
    Ingest all .txt files from eval_data/policy_docs/ into Pinecone.
    Returns a summary of what was ingested.
    """
    from app.rag.embedder import get_embeddings_batch

    if docs_dir is None:
        root = Path(__file__).resolve().parents[3]
        docs_dir = root / "eval_data" / "policy_docs"
    else:
        docs_dir = Path(docs_dir)

    if not docs_dir.exists():
        raise FileNotFoundError(f"Policy docs directory not found: {docs_dir}")

    txt_files = list(docs_dir.glob("*.txt"))
    if not txt_files:
        raise ValueError(f"No .txt files found in {docs_dir}")

    logger.info("ingest_start", doc_count=len(txt_files), dir=str(docs_dir))

    all_chunks = []
    for file_path in txt_files:
        source_name = file_path.stem  # filename without extension
        text = load_text_file(file_path)
        chunks = chunk_text(text, source_name)
        all_chunks.extend(chunks)

    logger.info("total_chunks", count=len(all_chunks))

    # Embed all chunks
    texts = [c["text"] for c in all_chunks]
    embeddings = get_embeddings_batch(texts)

    # Upsert to Pinecone
    upserted = upsert_chunks_to_pinecone(all_chunks, embeddings)

    summary = {
        "docs_ingested": len(txt_files),
        "total_chunks": len(all_chunks),
        "vectors_upserted": upserted,
        "sources": [f.stem for f in txt_files],
        "namespace": NAMESPACE,
    }
    logger.info("ingest_complete", **summary)
    return summary


if __name__ == "__main__":
    result = ingest_documents()
    print(result)