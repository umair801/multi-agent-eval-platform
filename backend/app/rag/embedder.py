# ============================================================
# AgAI_31: Embedder — OpenAI text-embedding-3-small
# ============================================================

import os
import time
from typing import Union
import openai
import structlog

logger = structlog.get_logger()

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


def get_embedding(text: str, retries: int = 3) -> list[float]:
    """
    Get OpenAI embedding for a single text string.
    Retries up to 3 times on rate limit errors.
    """
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    for attempt in range(retries):
        try:
            response = client.embeddings.create(
                model=EMBED_MODEL,
                input=text.strip(),
            )
            return response.data[0].embedding
        except openai.RateLimitError:
            wait = 2 ** attempt
            logger.warning("embed_rate_limit", attempt=attempt + 1, wait=wait)
            time.sleep(wait)
        except Exception as e:
            logger.error("embed_error", error=str(e))
            raise

    raise RuntimeError(f"Failed to embed text after {retries} attempts.")


def get_embeddings_batch(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    """
    Embed a list of texts in batches. Returns list of embedding vectors.
    """
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = [t.strip() for t in texts[i:i + batch_size]]
        try:
            response = client.embeddings.create(
                model=EMBED_MODEL,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            logger.info("batch_embedded", batch_start=i, batch_size=len(batch))
        except Exception as e:
            logger.error("batch_embed_error", batch_start=i, error=str(e))
            raise

    return all_embeddings