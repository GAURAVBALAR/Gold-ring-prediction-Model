import os
import time
from typing import Optional, List, Dict, Any
from pinecone import Pinecone, ServerlessSpec
from app.core.config import settings
from loguru import logger

_pinecone_index = None

def get_index():
    global _pinecone_index
    if _pinecone_index is None:
        api_key = settings.PINECONE_API_KEY or os.getenv("PINECONE_API_KEY")
        index_name = settings.PINECONE_INDEX_NAME or os.getenv("PINECONE_INDEX_NAME", "ring-designs-v2")
        if not api_key:
            logger.error("PINECONE_API_KEY not set")
            return None
        try:
            pc = Pinecone(api_key=api_key)
            
            # Check if index exists, create if not
            existing_indexes = [index.name for index in pc.list_indexes()]
            if index_name not in existing_indexes:
                from app.core.embeddings import get_embedding_dimension
                dim = get_embedding_dimension()
                logger.info(f"Creating Pinecone index: {index_name} with dimension: {dim}")
                pc.create_index(
                    name=index_name,
                    dimension=dim,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                # Wait for index to be ready
                while not pc.describe_index(index_name).status['ready']:
                    time.sleep(1)
            
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
    """
    index = get_index()
    if index is None:
        logger.warning("Pinecone index not available, returning empty query results.")
        return []

    # 1. Build Pinecone metadata filter
    filters = {}
    if ring_size is not None:
        filters["ring_size"] = {
            "$gte": float(ring_size) - 0.5,
            "$lte": float(ring_size) + 0.5
        }

    try:
        fetch_k = top_k * 2 if style else top_k
        query_kwargs = {
            "vector": embedding,
            "top_k": fetch_k,
            "include_metadata": True,
        }
        if filters:
            query_kwargs["filter"] = filters

        logger.info(f"Querying Pinecone index with filter: {filters} (fetch_k={fetch_k})")
        response = index.query(**query_kwargs)
        results = response.matches if hasattr(response, "matches") else []

        # Filter out results with score < min_similarity
        results = [r for r in results if r.score >= min_similarity]

        # 4. If results < 3 after filtering, retry WITHOUT the metadata filter
        if len(results) < 3:
            logger.warning(f"Filtered pool has only {len(results)} results (expected >= 3). Retrying WITHOUT metadata filter...")
            fallback_query_kwargs = {
                "vector": embedding,
                "top_k": top_k,
                "include_metadata": True,
            }
            response = index.query(**fallback_query_kwargs)
            results = response.matches if hasattr(response, "matches") else []
            results = [r for r in results if r.score >= min_similarity]

        # 5. Post-retrieval style boost: sort by score + 0.05 if metadata.ring_style == style.lower()
        if style and results:
            style_norm = str(style).lower().strip()

            def style_score(r):
                r_meta = r.metadata or {}
                r_style = str(r_meta.get("ring_style", "")).lower().strip()
                boost = 0.05 if r_style == style_norm else 0.0
                return r.score + boost

            results = sorted(results, key=style_score, reverse=True)

        # 6. Return top_k as list of dicts: {id, score, metadata}
        return [
            {
                "id": str(r.id),
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
    Upsert a verified ring design to Pinecone index with metadata.
    """
    index = get_index()
    if index is None:
        logger.error("Pinecone index not available for upsert.")
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
        
        # Include ring_size and ring_style in metadata (skip if None/NaN/empty)
        import pandas as pd
        if ring_size is not None and not pd.isna(ring_size):
            metadata["ring_size"] = float(ring_size)
        if ring_style is not None and str(ring_style).strip():
            metadata["ring_style"] = str(ring_style).lower().strip()

        logger.info(f"Upserting verified ring metadata for {product_id}: {metadata}")
        index.upsert(vectors=[{
            "id": str(product_id),
            "values": embedding,
            "metadata": metadata,
        }])
        return True
    except Exception as e:
        logger.error(f"Pinecone upsert error: {e}")
        return False

class PineconeDB:
    """
    Object wrapper to maintain backward-compatibility with app.db.chroma_client get_vector_db().
    """
    def __init__(self):
        # Initialise database connection
        get_index()

    def add_prediction(self, prediction_id: str, embedding: list, metadata: dict):
        """
        Add a prediction record to Pinecone. Maps metadata keys to upsert.
        """
        product_name = metadata.get("product_name", "Unknown Ring")
        actual_weight = metadata.get("actual_weight_g") or metadata.get("predicted_weight_14k") or 0.0
        actual_volume = metadata.get("actual_volume_mm3") or metadata.get("predicted_volume_mm3") or 0.0
        karat = metadata.get("karat", "18K")
        ring_size = metadata.get("ring_size")
        ring_style = metadata.get("ring_style") or metadata.get("style")
        diamond_carats = metadata.get("diamond_weight_carats") or metadata.get("stone_ct") or 0.0

        upsert_verified_ring(
            product_id=prediction_id,
            embedding=embedding,
            product_name=product_name,
            actual_weight_g=actual_weight,
            actual_volume_mm3=actual_volume,
            karat=karat,
            ring_size=ring_size,
            ring_style=ring_style,
            diamond_carats=diamond_carats
        )

    def query_similar(self, embedding: list, n_results: int = 5):
        """
        Query similar results. Returns backwards-compatible schema format.
        """
        # Call query_similar_rings with defaults
        results = query_similar_rings(embedding, top_k=n_results)
        
        # Format results into the older dict format
        formatted = []
        for r in results:
            meta = r.get("metadata", {})
            weight = meta.get("actual_weight_g") or meta.get("predicted_weight_14k") or meta.get("predicted_weight_18k")
            karat = str(meta.get("karat", "18K")).upper()
            stone_ct = meta.get("diamond_weight_carats") or meta.get("stone_ct") or 0.0

            vol = meta.get("actual_volume_mm3")
            if vol is None and weight is not None:
                from app.core.constants import GOLD_DENSITIES as GD
                density = GD.get(karat, 15.58)
                vol = weight / density if density else 0.0

            formatted.append({
                "product_id": meta.get("product_id") or r.get("id"),
                "product_name": meta.get("product_name", "Unknown Ring"),
                "params": {
                    "ring_size": meta.get("ring_size"),
                    "stone_ct": stone_ct,
                    "side_stone_count": meta.get("side_stone_count", 0),
                    "metal_color": meta.get("metal_color"),
                    "karat": karat
                },
                "actual_weight": weight,
                "actual_volume_mm3": vol,
                "score": r.get("score", 0.0)
            })
        return formatted
