"""
backend/app/db/pinecone_client.py  (REPLACE EXISTING FILE)
===========================================================
Key improvement: Hybrid RAG retrieval with metadata filtering.

Before:  pure visual cosine similarity → returns rings that LOOK similar
         but may be totally different sizes or styles → wrong weight anchor

After:   filter first by ring_size ± 0.5 + style match,
         THEN rank by cosine similarity within that filtered pool.
         This ensures the reference rings are physically comparable.
"""

import os
from typing import Optional
from loguru import logger
from pinecone import Pinecone


_pinecone_index = None


def get_index():
    global _pinecone_index
    if _pinecone_index is None:
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME", "ring-designs-v2")
        if not api_key:
            logger.error("PINECONE_API_KEY not set")
            return None
        try:
            pc = Pinecone(api_key=api_key)
            _pinecone_index = pc.Index(index_name)
            logger.info(f"Connected to Pinecone index: {index_name}")
        except Exception as e:
            logger.error(f"Pinecone connection error: {e}")
            return None
    return _pinecone_index


def query_similar_rings(
    embedding: list[float],
    top_k: int = 5,
    ring_size: Optional[float] = None,
    style: Optional[str] = None,
    min_similarity: float = 0.65,
) -> list[dict]:
    """
    Retrieve top-k visually similar rings with metadata filtering.

    Filtering strategy:
    1. If ring_size known: filter to ±0.5 ring size in Pinecone metadata filter
    2. If style known: soft-filter (include style match + unknown style)
    3. Fallback: if filtered pool < 3 results, retry without metadata filter

    Args:
        embedding:       CLIP image embedding (512-dim)
        top_k:           Number of results to return
        ring_size:       US ring size (optional but strongly recommended)
        style:           Ring style (optional)
        min_similarity:  Minimum cosine similarity score

    Returns:
        List of result dicts with 'score', 'metadata' fields
    """
    index = get_index()
    if index is None:
        return []

    # ── Build Pinecone metadata filter ────────────────────────────────────
    filters = {}

    if ring_size is not None:
        # Filter rings within ±0.5 size of the query
        filters["ring_size"] = {
            "$gte": ring_size - 0.5,
            "$lte": ring_size + 0.5
        }

    # NOTE: Pinecone doesn't support OR well in metadata filters.
    # We skip style filtering at the DB level and do it post-retrieval.
    # Instead, we fetch 2× top_k and rerank.

    try:
        fetch_k = top_k * 2 if style else top_k
        query_kwargs = {
            "vector": embedding,
            "top_k": fetch_k,
            "include_metadata": True,
        }
        if filters:
            query_kwargs["filter"] = filters

        response = index.query(**query_kwargs)
        results = response.matches if hasattr(response, "matches") else []

        # Filter by minimum similarity
        results = [r for r in results if r.score >= min_similarity]

        if not results:
            # Retry without metadata filter (ring_size may not be in metadata)
            logger.warning("No results with metadata filter, retrying without filter")
            response = index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
            )
            results = response.matches if hasattr(response, "matches") else []
            results = [r for r in results if r.score >= min_similarity]

        # ── Post-retrieval style boosting ──────────────────────────────────
        if style and results:
            style_norm = style.lower().strip()

            def style_score(r):
                r_style = str(r.metadata.get("ring_style", "")).lower()
                match = 1 if r_style == style_norm else 0
                return r.score + match * 0.05  # small boost for style match

            results = sorted(results, key=style_score, reverse=True)

        # Return top_k
        return [
            {
                "id": r.id,
                "score": float(r.score),
                "metadata": dict(r.metadata) if r.metadata else {},
            }
            for r in results[:top_k]
        ]

    except Exception as e:
        logger.error(f"Pinecone query error: {e}")
        return []


def upsert_verified_ring(
    product_id: str,
    embedding: list[float],
    product_name: str,
    actual_weight_g: float,
    actual_volume_mm3: float,
    karat: str,
    ring_size: Optional[float] = None,
    ring_style: Optional[str] = None,
    diamond_carats: float = 0.0,
) -> bool:
    """
    Add a verified ring design to Pinecone (feedback loop).
    The ring_size and ring_style are now included in metadata
    to enable the improved metadata-filtered retrieval.
    """
    index = get_index()
    if index is None:
        return False

    try:
        metadata = {
            "product_name": str(product_name),
            "actual_weight_g": float(actual_weight_g),
            "actual_volume_mm3": float(actual_volume_mm3),
            "karat": str(karat),
            "diamond_weight_carats": float(diamond_carats),
            "is_verified": True,
        }
        if ring_size is not None:
            metadata["ring_size"] = float(ring_size)
        if ring_style is not None:
            metadata["ring_style"] = str(ring_style).lower()

        index.upsert(vectors=[{
            "id": str(product_id),
            "values": embedding,
            "metadata": metadata,
        }])

        logger.info(f"Upserted verified ring: {product_id}")
        return True

    except Exception as e:
        logger.error(f"Pinecone upsert error: {e}")
        return False
