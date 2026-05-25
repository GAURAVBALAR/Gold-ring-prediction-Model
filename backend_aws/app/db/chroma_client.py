import chromadb
from app.core.config import settings
from loguru import logger
import os

class ChromaDB:
    def __init__(self):
        os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="ring_designs",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB initialized at {settings.CHROMA_DB_PATH}")

    def add_prediction(self, prediction_id: str, embedding: list, metadata: dict):
        # Filter out None values for Chroma metadata
        clean_metadata = {k: v for k, v in metadata.items() if v is not None}
        self.collection.add(
            ids=[str(prediction_id)],
            embeddings=[embedding],
            metadatas=[clean_metadata]
        )
        logger.info(f"Added record {prediction_id} to ChromaDB")

    def query_similar(self, embedding: list, n_results: int = 5):
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results
        )
        
        formatted = []
        if results['metadatas'] and results['metadatas'][0]:
            for i, meta in enumerate(results['metadatas'][0]):
                weight = meta.get("actual_weight_g") or meta.get("predicted_weight_14k")
                stone_ct = meta.get("diamond_weight_carats") or meta.get("stone_ct") or 0.0
                
                formatted.append({
                    "product_id": meta.get("product_id"),
                    "product_name": meta.get("product_name", "Unknown Ring"),
                    "params": {
                        "ring_size": meta.get("ring_size"),
                        "stone_ct": stone_ct,
                        "side_stone_count": meta.get("side_stone_count", 0),
                        "metal_color": meta.get("metal_color"),
                        "karat": meta.get("karat")
                    },
                    "actual_weight": weight
                })
        return formatted

# Singleton instance
vector_db = None

def get_vector_db():
    global vector_db
    if vector_db is None:
        if settings.VECTOR_DB_TYPE == "pinecone":
            from app.db.pinecone_client import PineconeDB
            vector_db = PineconeDB()
        else:
            vector_db = ChromaDB()
    return vector_db
