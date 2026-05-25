from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.prediction import Prediction
from app.models.schemas import PredictionResponse, UnifiedPredictionResponse, VerifiedDesignCreate, VerifiedDesignResponse, PredictionFeedback
from app.api.llm_utils import predict_gold_weight as llm_predict_gold_weight
from app.api import xgboost_predictor
from app.db.pinecone_client import query_similar_rings
from app.core.config import settings as app_settings
from app.core.constants import GOLD_DENSITIES
from app.core.embeddings import get_image_embedding, get_text_embedding
from app.core.xgboost_inference import predict_volume as xgb_predict, ensemble_volume
from app.db.chroma_client import get_vector_db
import json
import os
import uuid
import csv
import io
from loguru import logger
from typing import List

router = APIRouter()

@router.post("/search", response_model=list[dict])
async def search_similar_rings(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    RAG Endpoint: Send an image to find the top-5 visually similar rings 
    from the Tanishq dataset and previous predictions.
    """
    try:
        # Fetch dynamic settings from DB
        from sqlalchemy import select
        from app.models.settings import SystemSetting
        stmt = select(SystemSetting)
        result = await db.execute(stmt)
        config = {s.key: s.value for s in result.scalars().all()}
        gemini_key = config.get("gemini_api_key") or app_settings.GEMINI_API_KEY

        image_bytes = await image.read()
        vdb = get_vector_db()
        
        embedding = await get_image_embedding(image_bytes, gemini_key)
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
    style: str = Form(None),
    karat: str = Form("18K"),
    product_name: str = Form(""),
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
        
        # Fetch dynamic settings from DB early
        from sqlalchemy import select
        from app.models.settings import SystemSetting
        stmt = select(SystemSetting)
        settings_result = await db.execute(stmt)
        config = {s.key: s.value for s in settings_result.scalars().all()}
        gemini_key = config.get("gemini_api_key") or app_settings.GEMINI_API_KEY

        # 1. Visual RAG Search (Metadata Filtered)
        logger.info("Encoding primary image...")
        embedding = await get_image_embedding(all_image_bytes[0], gemini_key)
        
        logger.info(f"Querying visually similar rings for ring_size={ring_size}, style={style}...")
        similar_raw = query_similar_rings(
            embedding=embedding,
            top_k=5,
            ring_size=ring_size,
            style=style
        )
        
        # Format similar examples for downstream schema compatibility
        similar_examples = []
        for r in similar_raw:
            meta = r.get("metadata", {})
            score = r.get("score", 0.0)
            weight = meta.get("actual_weight_g") or meta.get("predicted_weight_14k") or meta.get("predicted_weight_18k")
            karat_val = str(meta.get("karat", "18K")).upper()
            stone_ct_val = meta.get("diamond_weight_carats") or meta.get("stone_ct") or 0.0
            
            vol = meta.get("actual_volume_mm3")
            if vol is None and weight is not None:
                density = GOLD_DENSITIES.get(karat_val, 15.58)
                vol = (weight / density) * 1000.0 if density else 0.0
            elif vol is not None:
                vol = float(vol)
                
            similar_examples.append({
                "product_id": meta.get("product_id") or r.get("id"),
                "product_name": meta.get("product_name", "Unknown Ring"),
                "params": {
                    "ring_size": meta.get("ring_size"),
                    "stone_ct": stone_ct_val,
                    "side_stone_count": meta.get("side_stone_count", 0),
                    "metal_color": meta.get("metal_color"),
                    "karat": karat_val
                },
                "actual_weight": float(weight) if weight is not None else 0.0,
                "actual_volume_mm3": float(vol) if vol is not None else 0.0,
                "score": float(score)
            })
            
        logger.info(f"Retrieved {len(similar_examples)} reference designs.")
        
        # 2. Local XGBoost Inference (Convert karat string to int)
        karat_clean = str(karat).upper().strip()
        import re
        karat_match = re.search(r"(\d+)", karat_clean)
        karat_int = int(karat_match.group(1)) if karat_match else 18
        
        logger.info(f"Running XGBoost tabular inference: ring_size={ring_size}, style={style}, karat={karat_int}, name={product_name}")
        xgb_pred = xgboost_predictor.predict_14k(
            ring_size=ring_size,
            style=style,
            original_karat=karat_int,
            product_name=product_name,
            source="unknown"
        )
        
        from google import genai
        client = None
        if gemini_key:
            client = genai.Client(api_key=gemini_key, http_options={'api_version': 'v1beta'})
            
        # 3. Core Estimation with Two-Stage Pipeline
        logger.info("Invoking two-stage LLM prediction and refinement pipeline...")
        result = await llm_predict_gold_weight(
            client=client,
            images=all_image_bytes,
            ring_size=ring_size,
            style=style,
            karat=karat_int,
            rag_results=similar_raw,
            xgboost_prediction=xgb_pred
        )
        
        # 4. Save to Database
        logger.info("Saving prediction to SQLite database...")
        new_prediction = Prediction(
            ring_size=ring_size,
            inner_diameter_mm=inner_diameter_mm or result["geometry"].get("band_width_mm"),
            band_width_mm=band_width_mm or result["geometry"].get("band_width_mm"),
            band_thickness_mm=band_thickness_mm or result["geometry"].get("band_thickness_mm"),
            stone_length_mm=stone_length_mm,
            stone_width_mm=stone_width_mm,
            stone_ct=stone_ct,
            side_stone_count=side_stone_count,
            side_stone_ct=side_stone_ct,
            image_path=image_paths[0],
            estimated_volume_mm3=result["safe_volume_mm3"],
            predicted_weight_14k=result["predicted_weight_14k"],
            predicted_weight_18k=result["predicted_weight_18k"],
            min_weight_14k=result["min_weight_14k"],
            max_weight_14k=result["max_weight_14k"],
            min_weight_18k=result["min_weight_18k"],
            max_weight_18k=result["max_weight_18k"],
            min_weight_22k=result["min_weight_22k"],
            max_weight_22k=result["max_weight_22k"],
            llm_explanation=result["explanation"],
            raw_response={
                "llm_raw": result["raw"],
                "rag_results": similar_examples,
                "ensemble": {
                    "sources": {
                        "llm_rag": result["safe_volume_mm3"],
                        "xgb_14k": (xgb_pred * 1000.0 / 13.07) if xgb_pred is not None else 0.0
                    },
                    "weights": {
                        "llm_rag": 0.80 if result["ensemble_applied"] else 1.00,
                        "xgb_14k": 0.20 if result["ensemble_applied"] else 0.00
                    },
                    "ensemble_applied": result["ensemble_applied"],
                    "confidence": result["confidence"]
                }
            }
        )
        db.add(new_prediction)
        await db.commit()
        await db.refresh(new_prediction)
        
        # 5. Add to Vector DB for future retrieval (only if prediction succeeded)
        if result["predicted_weight_14k"] > 0:
            rag_metadata = {k: v for k, v in params.items() if v is not None}
            rag_metadata.update({
                "product_name": product_name or "Predict-Generated Ring",
                "predicted_volume_mm3": float(result["safe_volume_mm3"]),
                "predicted_weight_14k": float(result["predicted_weight_14k"]),
                "predicted_weight_18k": float(result["predicted_weight_18k"]),
                "ring_size": float(ring_size) if ring_size else 7.0,
                "ring_style": str(result["geometry"].get("ring_style", style or "other")).lower(),
                "is_ai_generated": True
            })
            vdb = get_vector_db()
            vdb.add_prediction(
                prediction_id=str(new_prediction.id),
                embedding=embedding,
                metadata=rag_metadata
            )
            
        return {
            "prediction": new_prediction,
            "similar_examples": similar_examples,
            "xgboost_prediction_14k": xgb_pred,
            "ensemble_applied": result["ensemble_applied"]
        }
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_prediction_feedback(
    feedback: PredictionFeedback,
    db: AsyncSession = Depends(get_db)
):
    """
    User feedback endpoint: Converts actual weight to volume/density 
    and updates the Vector DB for better future RAG accuracy.
    """
    try:
        from sqlalchemy import select
        result = await db.execute(select(Prediction).where(Prediction.id == feedback.prediction_id))
        prediction = result.scalar_one_or_none()

        if not prediction:
            raise HTTPException(status_code=404, detail="Prediction not found")

        # 1. Update SQL record if weight provided
        if feedback.actual_weight_g and feedback.actual_karat:
            density = GOLD_DENSITIES.get(feedback.actual_karat.upper(), GOLD_DENSITIES["18K"])
            actual_volume = feedback.actual_weight_g / density

            # Store in structured columns
            prediction.actual_weight_g = feedback.actual_weight_g
            prediction.actual_karat = feedback.actual_karat
            prediction.llm_explanation += f"\n\n[USER FEEDBACK]: Actual weight {feedback.actual_weight_g}g ({feedback.actual_karat})."
            # Capture attributes and dynamic settings before db.commit() expires them
            image_path = prediction.image_path
            prediction_id = prediction.id

            from sqlalchemy import select
            from app.models.settings import SystemSetting
            stmt = select(SystemSetting)
            settings_result = await db.execute(stmt)
            config = {s.key: s.value for s in settings_result.scalars().all()}
            gemini_key = config.get("gemini_api_key") or app_settings.GEMINI_API_KEY

            await db.commit()

            # 2. Re-encode and update Vector DB with CORRECT data
            # This makes the "memory" much more accurate
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_bytes = f.read()

                vdb = get_vector_db()
                embedding = await get_image_embedding(image_bytes, gemini_key)

                vdb.add_prediction(
                    prediction_id=str(prediction_id),
                    embedding=embedding,
                    metadata={
                        "product_id": f"fb_{prediction_id}",
                        "actual_weight_g": feedback.actual_weight_g,
                        "actual_volume_mm3": actual_volume,
                        "karat": feedback.actual_karat,
                        "diamond_weight_carats": feedback.actual_diamond_carat,
                        "is_verified": True
                    }
                )
                logger.info(f"Updated Vector DB with user feedback for prediction {prediction_id}")

        return {"status": "success", "message": "Feedback recorded and indexed"}
    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
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
    from sqlalchemy import select
    from app.models.settings import SystemSetting
    stmt = select(SystemSetting)
    settings_result = await db.execute(stmt)
    config = {s.key: s.value for s in settings_result.scalars().all()}
    gemini_key = config.get("gemini_api_key") or app_settings.GEMINI_API_KEY

    vdb = get_vector_db()
    embedding = await get_image_embedding(image_bytes, gemini_key)
    
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


@router.post("/predict-ml", response_model=UnifiedPredictionResponse)
async def predict_gold_weight_ml(
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
    """
    ML-Only endpoint: Predict Gold Weight using local RAG + XGBoost (no LLM reasoning).
    """
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
        logger.info(f"Starting ML prediction process with {len(all_image_bytes)} images...")
        
        # Fetch dynamic settings from DB early
        from sqlalchemy import select
        from app.models.settings import SystemSetting
        stmt = select(SystemSetting)
        settings_result = await db.execute(stmt)
        config = {s.key: s.value for s in settings_result.scalars().all()}
        gemini_key = config.get("gemini_api_key") or app_settings.GEMINI_API_KEY

        vdb = get_vector_db()
        
        logger.info("Encoding primary image...")
        embedding = await get_image_embedding(all_image_bytes[0], gemini_key)
        
        logger.info("Querying similar rings...")
        similar_examples = vdb.query_similar(embedding)
        
        # Inject Volume into examples if missing
        for ex in similar_examples:
            if "actual_volume_mm3" not in ex:
                density = GOLD_DENSITIES.get(ex.get("karat", "18K").upper(), GOLD_DENSITIES["18K"])
                ex["actual_volume_mm3"] = ex["actual_weight"] / density

        logger.info(f"Retrieved {len(similar_examples)} similar examples from Vector DB")
        
        rag_volumes = [ex.get("actual_volume_mm3") for ex in similar_examples if ex.get("actual_volume_mm3") is not None]
        if rag_volumes:
            fast_path_volume = sum(rag_volumes[:3]) / min(3, len(rag_volumes))
        else:
            fast_path_volume = 192.56  # default ~3.0g for 18K
            
        # Run XGBoost prediction using RAG baseline weight
        baseline_weight_18k = fast_path_volume * GOLD_DENSITIES["18K"]
        xgb_result = xgb_predict(
            gold_weight_grams=baseline_weight_18k,
            karat="18K",
            diamond_carat=stone_ct or 0,
            product_name="ring",
            image_count=len(all_image_bytes)
        )
        xgb_volume = xgb_result["volume_mm3"] if xgb_result else fast_path_volume
        
        # Blend RAG and XGBoost (60/40)
        final_volume = 0.60 * fast_path_volume + 0.40 * xgb_volume
        ensemble = {
            "sources": {"rag": fast_path_volume, "xgb": xgb_volume},
            "weights": {"rag": 0.60, "xgb": 0.40},
            "profile_used": "ml_only"
        }
        
        final_w14k = final_volume * GOLD_DENSITIES["14K"]
        final_w18k = final_volume * GOLD_DENSITIES["18K"]
        final_w22k = final_volume * GOLD_DENSITIES["22K"]
        
        prediction_data = {
            "estimated_volume_mm3": final_volume,
            "predicted_weight_14k": final_w14k,
            "predicted_weight_18k": final_w18k,
            "predicted_weight_22k": final_w22k,
            "min_weight_14k": final_w14k * 0.95,
            "max_weight_14k": final_w14k * 1.10,
            "min_weight_18k": final_w18k * 0.95,
            "max_weight_18k": final_w18k * 1.10,
            "min_weight_22k": final_w22k * 0.95,
            "max_weight_22k": final_w22k * 1.10,
            "explanation": "ML-only prediction using RAG similarity and XGBoost regressor (no LLM reasoning).",
            "raw": {
                "confidence": "medium",
                "confidence_note": "ML-only prediction using local models.",
                "fast_path": True,
                "volume_breakdown": {
                    "shank_mm3": final_volume * 0.70,
                    "head_setting_mm3": final_volume * 0.20,
                    "gallery_mm3": final_volume * 0.05,
                    "side_stone_channels_mm3": final_volume * 0.05,
                    "calculation_steps": "ML-only estimation. Default component volumes applied."
                }
            }
        }
        
        logger.info("Saving prediction to database...")
        new_prediction = Prediction(
            **params,
            image_path=image_paths[0],
            estimated_volume_mm3=final_volume,
            predicted_weight_14k=final_w14k,
            predicted_weight_18k=final_w18k,
            min_weight_14k=prediction_data["min_weight_14k"],
            max_weight_14k=prediction_data["max_weight_14k"],
            min_weight_18k=prediction_data["min_weight_18k"],
            max_weight_18k=prediction_data["max_weight_18k"],
            min_weight_22k=prediction_data["min_weight_22k"],
            max_weight_22k=prediction_data["max_weight_22k"],
            llm_explanation=prediction_data["explanation"],
            raw_response={
                "llm_raw": prediction_data["raw"],
                "rag_results": similar_examples,
                "ensemble": ensemble,
                "xgb_result": xgb_result,
            }
        )
        
        db.add(new_prediction)
        await db.commit()
        await db.refresh(new_prediction)
        
        # Add to Vector DB for future retrieval
        rag_metadata = {k: v for k, v in params.items() if v is not None}
        rag_metadata.update({
            "predicted_volume_mm3": float(final_volume),
            "predicted_weight_14k": float(final_w14k),
            "predicted_weight_18k": float(final_w18k),
            "is_ai_generated": True,
            "is_fast_path": True
        })

        vdb.add_prediction(
            prediction_id=str(new_prediction.id),
            embedding=embedding,
            metadata=rag_metadata
        )
        
        return {
            "prediction": new_prediction,
            "similar_examples": similar_examples
        }
    except Exception as e:
        logger.error(f"ML prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/export")
async def export_prediction_history(db: AsyncSession = Depends(get_db)):
    """
    Exports the prediction history to a CSV file.
    """
    try:
        from sqlalchemy import select
        result = await db.execute(select(Prediction).order_by(Prediction.created_at.desc()))
        predictions = result.scalars().all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            "ID", "Date", "Ring Size", "Inner Diameter (mm)", "Band Width (mm)", 
            "Band Thickness (mm)", "Stone Length (mm)", "Stone Width (mm)", 
            "Stone Carat (ct)", "Side Stone Count", "Side Stone Carats", 
            "Estimated Volume (mm3)", "Predicted Weight 14K (g)", "Predicted Weight 18K (g)",
            "Actual Weight (g)", "Actual Karat", "Explanation"
        ])
        
        for p in predictions:
            writer.writerow([
                p.id,
                p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
                p.ring_size if p.ring_size is not None else "",
                p.inner_diameter_mm if p.inner_diameter_mm is not None else "",
                p.band_width_mm if p.band_width_mm is not None else "",
                p.band_thickness_mm if p.band_thickness_mm is not None else "",
                p.stone_length_mm if p.stone_length_mm is not None else "",
                p.stone_width_mm if p.stone_width_mm is not None else "",
                p.stone_ct if p.stone_ct is not None else "",
                p.side_stone_count if p.side_stone_count is not None else 0,
                p.side_stone_ct if p.side_stone_ct is not None else 0.0,
                f"{p.estimated_volume_mm3:.3f}" if p.estimated_volume_mm3 is not None else "",
                f"{p.predicted_weight_14k:.3f}" if p.predicted_weight_14k is not None else "",
                f"{p.predicted_weight_18k:.3f}" if p.predicted_weight_18k is not None else "",
                f"{p.actual_weight_g:.3f}" if p.actual_weight_g is not None else "",
                p.actual_karat if p.actual_karat else "",
                p.llm_explanation or ""
            ])
            
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=gold_weight_predictions_history.csv"}
        )
    except Exception as e:
        logger.error(f"Failed to export prediction history: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
