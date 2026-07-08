"""
Embedding generation for Lexy's RAG pipeline.

Uses an OpenAI-compatible API (configurable via .env).
Groq does not serve embedding models, so this must be a separate API.
Configure EMBEDDING_API_KEY, EMBEDDING_URL, EMBEDDING_MODEL in .env.
"""

import logging

from config import EMBEDDING_API_KEY, EMBEDDING_URL, EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def generate_embedding(text: str) -> list[float] | None:
    """Generate an embedding vector for a single text string."""
    if not EMBEDDING_API_KEY:
        logger.warning("No EMBEDDING_API_KEY configured — cannot generate embeddings")
        return None
    try:
        import httpx
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EMBEDDING_MODEL,
                    "input": text,
                },
            )
        if resp.status_code != 200:
            logger.error("Embedding API error: %s %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        logger.warning("Failed to generate embedding: %s", e)
        return None


def generate_embeddings_batch(texts: list[str]) -> list[list[float]] | None:
    """Generate embeddings for multiple texts in one API call."""
    if not EMBEDDING_API_KEY:
        logger.warning("No EMBEDDING_API_KEY configured — cannot generate embeddings")
        return None
    if not texts:
        return []
    try:
        import httpx
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EMBEDDING_MODEL,
                    "input": texts,
                },
            )
        if resp.status_code != 200:
            logger.error("Embedding API error: %s %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        # Sort by index to preserve order
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]
    except Exception as e:
        logger.warning("Failed to generate embeddings batch: %s", e)
        return None
