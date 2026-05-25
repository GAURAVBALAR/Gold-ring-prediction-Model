import os
import sys
import pandas as pd
from PIL import Image
from tqdm import tqdm
import json

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.embeddings import get_clip_encoder
from app.db.pinecone_client import PineconeDB

# Density Mapping (g/mm3)
GOLD_DENSITIES = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930
}

def ingest():
    csv_path = "Tanishq_Jewelry_Dataset_Final/tanishq_jewelry_enriched.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found. Run preprocess_dataset.py first.")
        return

    df = pd.read_csv(csv_path)
    encoder = get_clip_encoder()
    vdb = PineconeDB()

    print(f"Starting ingestion of {len(df)} products...")

    for idx, row in tqdm(df.iterrows(), total=len(df)):
        image_paths = str(row['local_image_paths']).split('|')
        if not image_paths or not os.path.exists(image_paths[0]):
            continue
        
        try:
            # Load primary image
            with open(image_paths[0], "rb") as f:
                img_bytes = f.read()
            
            # Generate embedding
            embedding = encoder.get_image_embedding(img_bytes)
            
            # Calculate Volume
            weight = float(row['gold_weight_grams'])
            karat = str(row['gold_karat_purity']).upper()
            density = GOLD_DENSITIES.get(karat, GOLD_DENSITIES["18K"])
            volume = weight / density

            # Prepare metadata
            metadata = {
                "product_id": str(row['product_id']),
                "product_name": str(row['product_name']),
                "actual_weight_g": weight,
                "actual_volume_mm3": volume,
                "karat": karat,
                "metal_color": str(row['metal_color']),
                "diamond_weight_carats": float(row['diamond_weight_carats']) if not pd.isna(row['diamond_weight_carats']) else 0.0,
                "stone_type": str(row['stone_type']),
                "source": "tanishq_dataset"
            }
            
            # Add to Vector DB
            vdb.add_prediction(
                prediction_id=str(row['product_id']),
                embedding=embedding,
                metadata=metadata
            )
            
        except Exception as e:
            print(f"Error processing {row['product_id']}: {e}")

    print("Ingestion complete.")

if __name__ == "__main__":
    ingest()
