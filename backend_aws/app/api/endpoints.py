from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.prediction import Prediction
from app.models.schemas import PredictionResponse, UnifiedPredictionResponse, VerifiedDesignCreate, VerifiedDesignResponse
from app.api.llm_utils import get_llm_prediction, GOLD_DENSITIES
from app.core.embeddings import embedding_manager
from app.db.pinecone_client import get_vector_db
import json
import os
import uuid
from loguru import logger

router = APIRouter()

@router.post("/search", response_model=list[dict])
async def search_similar_rings(
    image: UploadFile = File(...)
):
    """
    RAG Endpoint: Send an image to find the top-5 visually similar rings 
    from the Tanishq dataset and previous predictions.
    """
    try:
        image_bytes = await image.read()
        vdb = get_vector_db()

        embedding = await embedding_manager.get_image_embedding(image_bytes)
        similar_examples = vdb.query_similar(embedding)        
        return similar_examples
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from typing import List

@router.post("/predict", response_model=UnifiedPredictionResponse)
async def predict_gold_weight(
    ring_size: float = Form(None),
    inner_diameter_mm: float = Form(None),
    band_width_mm: float = Form(None),
    band_thickness_mm: float = Form(None),
    stone_length_mm: float = Form(None),
    stone_width_mm: float = Form(None),
    stone_ct: float = Form(None),
    side_stone_count: int = Form(0),
    side_stone_ct: float = Form(0.0),
    images: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Save images
    os.makedirs("data/images", exist_ok=True)
    image_paths = []
    all_image_bytes = []
    
    for img_file in images[:3]: # Limit to 3 images
        image_ext = os.path.splitext(img_file.filename)[1]
        image_filename = f"{uuid.uuid4()}{image_ext}"
        image_path = f"data/images/{image_filename}"
        
        content = await img_file.read()
        all_image_bytes.append(content)
        with open(image_path, "wb") as f:
            f.write(content)
        image_paths.append(image_path)
        
    params = {
        "ring_size": ring_size,
        "inner_diameter_mm": inner_diameter_mm,
        "band_width_mm": band_width_mm,
        "band_thickness_mm": band_thickness_mm,
        "stone_length_mm": stone_length_mm,
        "stone_width_mm": stone_width_mm,
        "stone_ct": stone_ct,
        "side_stone_count": side_stone_count,
        "side_stone_ct": side_stone_ct
    }
    
    try:
        logger.info(f"Starting prediction process with {len(all_image_bytes)} images...")
        # Phase 2: Vector Search
        vdb = get_vector_db()

        logger.info("Encoding primary image...")
        # We use the first image for visual RAG
        embedding = await embedding_manager.get_image_embedding(all_image_bytes[0])        
        logger.info("Querying similar rings...")
        similar_examples = vdb.query_similar(embedding)
        
        # Inject Volume into examples if missing (for legacy data)
        for ex in similar_examples:
            if "actual_volume_mm3" not in ex:
                density = GOLD_DENSITIES.get(ex.get("karat", "18K").upper(), GOLD_DENSITIES["18K"])
                ex["actual_volume_mm3"] = ex["actual_weight"] / density

        logger.info(f"Retrieved {len(similar_examples)} similar examples from Vector DB")
        
        # Fetch dynamic settings from DB
        logger.info("Fetching system settings...")
        from sqlalchemy import select
        from app.models.settings import SystemSetting
        stmt = select(SystemSetting)
        result = await db.execute(stmt)
        config = {s.key: s.value for s in result.scalars().all()}

        # Call LLM with all images
        logger.info(f"Calling LLM ({config.get('default_llm', 'default')})...")
        # NOTE: get_llm_prediction must be updated to handle List[bytes]
        prediction_data = await get_llm_prediction(all_image_bytes, params, config, similar_examples)
        
        logger.info("Saving prediction to database...")
        # Save to SQL DB (store first image path as primary)
        new_prediction = Prediction(
            **params,
            image_path=image_paths[0],
            estimated_volume_mm3=prediction_data.get("estimated_volume_mm3"),
            predicted_weight_14k=prediction_data["predicted_weight_14k"],
            predicted_weight_18k=prediction_data["predicted_weight_18k"],
            min_weight_14k=prediction_data.get("min_weight_14k"),
            max_weight_14k=prediction_data.get("max_weight_14k"),
            min_weight_18k=prediction_data.get("min_weight_18k"),
            max_weight_18k=prediction_data.get("max_weight_18k"),
            min_weight_22k=prediction_data.get("min_weight_22k"),
            max_weight_22k=prediction_data.get("max_weight_22k"),
            llm_explanation=prediction_data["explanation"],
            raw_response={
                "llm_raw": prediction_data["raw"],
                "rag_results": similar_examples
            }
        )
        
        db.add(new_prediction)
        await db.commit()
        await db.refresh(new_prediction)
        
        logger.info(f"Prediction saved with ID: {new_prediction.id}")
        
        # Phase 2: Add to Vector DB for future retrieval (only if prediction succeeded)
        if prediction_data["predicted_weight_14k"] > 0:
            chroma_metadata = {k: v for k, v in params.items() if v is not None}
            chroma_metadata.update({
                "predicted_weight_14k": float(prediction_data["predicted_weight_14k"]),
                "predicted_weight_18k": float(prediction_data["predicted_weight_18k"])
            })

            vdb.add_prediction(
                prediction_id=str(new_prediction.id),
                embedding=embedding,
                metadata=chroma_metadata
            )
        else:
            logger.warning("Prediction weight is 0.0, skipping Vector DB update.")
        
        # Return prediction + RAG results
        return {
            "prediction": new_prediction,
            "similar_examples": similar_examples
        }
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history", response_model=list[PredictionResponse])
async def get_prediction_history(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(Prediction).order_by(Prediction.created_at.desc()))
    return result.scalars().all()

@router.post("/ingest", response_model=VerifiedDesignResponse)
async def ingest_verified_design(
    product_name: str = Form(...),
    karat: str = Form(...), # e.g. "18K", "14K"
    actual_weight_g: float = Form(...),
    ring_size: float = Form(None),
    stone_ct: float = Form(0.0),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Adds a verified design to the training pool (RAG)."""
    # 1. Save Image
    os.makedirs("data/images", exist_ok=True)
    image_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
    image_path = os.path.join("data/images", image_filename)
    image_bytes = await image.read()
    
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    # 2. Calculate Volume from Weight/Karat (for internal reference)
    density = GOLD_DENSITIES.get(karat.upper(), GOLD_DENSITIES["18K"])
    estimated_volume = actual_weight_g / density

    # 3. Save to SQL
    from app.models.prediction import VerifiedDesign
    new_design = VerifiedDesign(
        product_name=product_name,
        karat=karat,
        actual_weight_g=actual_weight_g,
        estimated_volume_mm3=estimated_volume,
        ring_size=ring_size,
        stone_ct=stone_ct,
        image_path=image_path
    )
    db.add(new_design)
    await db.commit()
    await db.refresh(new_design)

    # 4. Add to Vector DB (RAG)
    vdb = get_vector_db()
    embedding = await embedding_manager.get_image_embedding(image_bytes)
    
    vdb.add_prediction(
        prediction_id=f"verified_{new_design.id}",
        embedding=embedding,
        metadata={
            "product_id": f"v_{new_design.id}",
            "product_name": product_name,
            "actual_weight_g": actual_weight_g,
            "actual_volume_mm3": estimated_volume,
            "karat": karat,
            "ring_size": ring_size,
            "stone_ct": stone_ct
        }
    )

    return new_design
