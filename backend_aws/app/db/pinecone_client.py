from pinecone import Pinecone, ServerlessSpec
from app.core.config import settings
from loguru import logger
import time
import json

# Density Mapping (g/mm3)
GOLD_DENSITIES = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930
}

class PineconeDB:
    def __init__(self):
        if not settings.PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not set in environment")
            
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index_name = settings.PINECONE_INDEX_NAME
        
        # Check if index exists, create if not
        existing_indexes = [index.name for index in self.pc.list_indexes()]
        if self.index_name not in existing_indexes:
            logger.info(f"Creating Pinecone index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=3072, # Gemini gemini-embedding-2 dimension
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # Wait for index to be ready
            while not self.pc.describe_index(self.index_name).status['ready']:
                time.sleep(1)
                
        self.index = self.pc.Index(self.index_name)
        logger.info(f"PineconeDB initialized with index {self.index_name}")

    def add_prediction(self, prediction_id: str, embedding: list, metadata: dict):
        import math
        clean_metadata = {}
        for k, v in metadata.items():
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                clean_metadata[k] = v

        self.index.upsert(
            vectors=[{
                "id": str(prediction_id),
                "values": embedding,
                "metadata": clean_metadata
            }]
        )
        logger.info(f"Added record {prediction_id} to Pinecone")

    def query_similar(self, embedding: list, n_results: int = 5):
        results = self.index.query(
            vector=embedding,
            top_k=n_results,
            include_metadata=True
        )
        
        formatted = []
        for match in results['matches']:
            meta = match['metadata']
            
            # Map dataset fields or prediction fields
            weight = meta.get("actual_weight_g") or meta.get("predicted_weight_14k")
            karat = str(meta.get("karat", "18K")).upper()
            
            # Use pre-calculated volume if available, otherwise calculate on the fly
            volume = meta.get("actual_volume_mm3")
            if volume is None and weight is not None:
                density = GOLD_DENSITIES.get(karat, GOLD_DENSITIES["18K"])
                volume = weight / density

            stone_ct = meta.get("diamond_weight_carats") or meta.get("stone_ct") or 0.0
            
            formatted.append({
                "product_id": meta.get("product_id"),
                "product_name": meta.get("product_name", "Unknown Ring"),
                "params": {
                    "ring_size": meta.get("ring_size"),
                    "stone_ct": stone_ct,
                    "side_stone_count": meta.get("side_stone_count", 0),
                    "metal_color": meta.get("metal_color"),
                    "karat": karat
                },
                "actual_weight": weight,
                "actual_volume_mm3": volume,
                "score": match['score']
            })
        return formatted

pinecone_db = None

def get_vector_db():
    global pinecone_db
    if pinecone_db is None:
        pinecone_db = PineconeDB()
    return pinecone_db
