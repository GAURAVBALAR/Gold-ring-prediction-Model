import os
import sys
from loguru import logger
import pandas as pd

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.config import settings
from app.db.pinecone_client import PineconeDB

# Density Mapping (g/mm3)
GOLD_DENSITIES = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930
}

def migrate_to_volume():
    logger.info("Starting Pinecone Metadata Migration to Volume-First...")
    vdb = PineconeDB()
    
    # Use absolute path to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(project_root, "Tanishq_Jewelry_Dataset_Final/tanishq_jewelry_enriched.csv")
    
    if not os.path.exists(csv_path):
        logger.error(f"Migration source {csv_path} not found.")
        return

    df = pd.read_csv(csv_path)
    updated_count = 0

    for idx, row in df.iterrows():
        product_id = str(row['product_id'])
        weight = float(row['gold_weight_grams'])
        karat = str(row['gold_karat_purity']).upper()
        
        # Get density
        density = GOLD_DENSITIES.get(karat, GOLD_DENSITIES["18K"])
        volume = weight / density
        
        # Fetch existing vector if possible, or just upsert with new metadata
        # Since we don't want to re-encode images (slow), we might need the original embeddings
        # BUT: Upsert in Pinecone overwrites. If we don't provide values, it might fail or clear them.
        
        # ACTUALLY: Pinecone's update() allows updating metadata without providing values!
        try:
            vdb.index.update(
                id=product_id,
                set_metadata={
                    "actual_volume_mm3": volume,
                    "actual_weight_g": weight,
                    "karat": karat
                }
            )
            updated_count += 1
            if updated_count % 100 == 0:
                logger.info(f"Updated {updated_count} records...")
        except Exception as e:
            # logger.error(f"Failed to update {product_id}: {e}")
            pass

    logger.info(f"Migration complete! Updated {updated_count} legacy records with Volume metadata.")

if __name__ == "__main__":
    migrate_to_volume()
