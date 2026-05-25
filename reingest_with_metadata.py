"""
reingest_with_metadata.py  (NEW FILE — run on EC2)
===================================================
Re-ingests the density dataset into Pinecone v2 index with IMPROVED metadata.
Critical upgrade: adds ring_size and ring_style to metadata so the new
query_similar_rings() can do metadata-filtered retrieval.

Run ONCE after upgrading the backend:
    python3 reingest_with_metadata.py

This does NOT delete the existing index — it upserts (overwrite by ID).
"""

import pandas as pd
import os
import time
import re
from pinecone import Pinecone, ServerlessSpec
from loguru import logger
import torch
import open_clip
from PIL import Image
from dotenv import load_dotenv

load_dotenv("./backend/.env")

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "ring-designs-v2"

device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32", pretrained="laion2b_s34b_b79k", device=device
)

# Ring style keywords for auto-detection
STYLE_KEYWORDS = {
    "solitaire": ["solitaire"],
    "halo": ["halo"],
    "band": ["band", "stackable"],
    "eternity": ["eternity"],
    "vintage": ["vintage", "antique", "milgrain", "filigree"],
    "bypass": ["bypass"],
    "cluster": ["cluster"],
    "cocktail": ["cocktail"],
    "bezel": ["bezel"],
    "chevron": ["chevron"],
    "infinity": ["infinity"],
    "promise": ["promise"],
}

def detect_style_from_name(name: str) -> str:
    name = name.lower()
    for style, keywords in STYLE_KEYWORDS.items():
        if any(k in name for k in keywords):
            return style
    return "other"

def get_image_embedding(image_path: str) -> list:
    try:
        img = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
        with torch.no_grad():
            feats = model.encode_image(img)
            feats /= feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().flatten().tolist()
    except Exception as e:
        logger.error(f"Error: {image_path}: {e}")
        return None


def ingest():
    pc    = Pinecone(api_key=PINECONE_API_KEY)

    if PINECONE_INDEX_NAME not in [i.name for i in pc.list_indexes()]:
        logger.info(f"Creating index {PINECONE_INDEX_NAME}")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=512,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
            time.sleep(1)

    index = pc.Index(PINECONE_INDEX_NAME)

    # Try both possible CSV paths
    csv_candidates = [
        "./backend/data/tanishq_density_dataset.csv",
        "./master_dataset.csv",
    ]
    df = None
    for p in csv_candidates:
        if os.path.exists(p):
            df = pd.read_csv(p)
            logger.info(f"Loaded {len(df)} records from {p}")
            break

    if df is None:
        logger.error("No CSV found. Run create_density_dataset.py first.")
        return

    # Normalise column names
    if "gold_weight_14k" in df.columns and "gold_weight_grams" not in df.columns:
        df["gold_weight_grams"] = df["gold_weight_14k"]

    if "design_volume_mm3" not in df.columns:
        # Calculate from weight using 18K density default
        GOLD_DENSITIES = {"14K": 13.07, "18K": 15.58, "22K": 17.50}
        def calc_vol(row):
            karat = str(row.get("original_karat", row.get("gold_karat_purity", 18)))
            k = f"{karat}K" if "K" not in str(karat) else str(karat)
            density = GOLD_DENSITIES.get(k, 15.58)
            return float(row["gold_weight_grams"]) / density * 1000
        df["design_volume_mm3"] = df.apply(calc_vol, axis=1)

    batch, batch_size = [], 50

    for i, row in df.iterrows():
        # Resolve image path
        local_path_col = "local_image_paths" if "local_image_paths" in df.columns else "local_image_path"
        raw_path = str(row.get(local_path_col, ""))
        first_path = raw_path.split("|")[0]
        filename = os.path.basename(first_path)

        candidates = [
            first_path,
            f"./Tanishq_Jewelry_Dataset_Final/images/uncategorized/{filename}",
            f"./rings_images/{filename}",
        ]
        actual_path = next((p for p in candidates if os.path.exists(p)), None)

        if actual_path is None:
            continue

        emb = get_image_embedding(actual_path)
        if emb is None:
            continue

        name     = str(row.get("product_name", ""))
        style    = detect_style_from_name(name)
        karat_raw = str(row.get("original_karat", row.get("gold_karat_purity", 18)))
        karat    = f"{karat_raw}K" if "K" not in karat_raw else karat_raw
        weight_g = float(row["gold_weight_grams"])
        vol_mm3  = float(row["design_volume_mm3"])
        ring_size = row.get("ring_size_us", None)

        meta = {
            "product_name":        name,
            "actual_weight_g":     weight_g,
            "actual_volume_mm3":   vol_mm3,
            "karat":               karat,
            "diamond_weight_carats": float(row.get("diamond_carat", row.get("diamond_weight_carats", 0)) or 0),
            "ring_style":          style,        # ← NEW: enables style-filtered RAG
            "is_verified":         True,
        }
        if ring_size is not None and not pd.isna(ring_size):
            meta["ring_size"] = float(ring_size)  # ← NEW: enables size-filtered RAG

        product_id = str(row.get("product_id", i))
        batch.append({"id": product_id, "values": emb, "metadata": meta})

        if len(batch) >= batch_size:
            index.upsert(vectors=batch)
            logger.info(f"Upserted {len(batch)} vectors (row {i})")
            batch = []

    if batch:
        index.upsert(vectors=batch)

    logger.info("Re-ingestion complete! ring_size and ring_style now in metadata.")


if __name__ == "__main__":
    ingest()
