"""
XGBoost Inference Module — Ensemble Integration
================================================

Loads the trained XGBoost model and provides volume predictions
from tabular features.  Used as one signal in the ensemble:
  final_volume = w_llm * llm_vol + w_rag * rag_vol + w_xgb * xgb_vol

The model is loaded lazily on first call and cached for the process
lifetime.
"""

import os
from pathlib import Path
from typing import Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy-loaded model singleton
# ---------------------------------------------------------------------------
_MODEL_CACHE: dict = {}

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "xgboost_v1.joblib"

GOLD_DENSITIES_XGB = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930,
}


def _load_model():
    """Load model once and cache it."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE

    if not MODEL_PATH.exists():
        logger.warning(f"XGBoost model not found at {MODEL_PATH}. Train it first.")
        return None

    try:
        import joblib
        artifact = joblib.load(MODEL_PATH)
        _MODEL_CACHE.update(artifact)
        logger.info(
            f"XGBoost model loaded — "
            f"CV MAE: {artifact['metrics']['cv_mae_mean']:.1f} mm³, "
            f"R²: {artifact['metrics']['cv_r2_mean']:.4f}"
        )
        return _MODEL_CACHE
    except Exception as e:
        logger.error(f"Failed to load XGBoost model: {e}")
        return None


# ---------------------------------------------------------------------------
# Feature extraction (mirrors train_xgboost.py)
# ---------------------------------------------------------------------------

def _extract_product_type(name: str) -> str:
    name_lower = name.lower()
    if "ring" in name_lower:
        return "ring_men" if "men" in name_lower else "ring"
    elif any(kw in name_lower for kw in ["earring", "stud", "jhumka", "hoop"]):
        return "earring"
    elif "pendant" in name_lower:
        return "pendant"
    elif any(kw in name_lower for kw in ["necklace", "chain"]):
        return "necklace"
    elif any(kw in name_lower for kw in ["bracelet", "bangle"]):
        return "bracelet"
    return "other"


def _extract_complexity(name: str) -> int:
    name_lower = name.lower()
    score = 2  # baseline
    simple = ["plain", "sleek", "minimal", "delicate", "simple", "slender"]
    complex_ = ["filigree", "sculpted", "ornate", "weave", "lattice",
                "geometric", "vintage", "layered", "interlaced", "floral",
                "cathedral", "halo", "cluster", "pave", "pavé"]
    for kw in simple:
        if kw in name_lower:
            score -= 1
    for kw in complex_:
        if kw in name_lower:
            score += 1
    return max(0, min(4, score))


def predict_volume(
    gold_weight_grams: float,
    karat: str = "18K",
    diamond_carat: float = 0.0,
    product_name: str = "ring",
    image_count: int = 1,
) -> Optional[dict]:
    """
    Predict design volume in mm³ from tabular features.

    Returns None if the model isn't available.
    Returns dict with 'volume_mm3' and per-karat weights.
    """
    artifact = _load_model()
    if artifact is None:
        return None

    import numpy as np
    import pandas as pd

    model = artifact["model"]
    imputer = artifact["imputer"]
    label_encoder = artifact["label_encoder"]
    feature_cols = artifact["feature_cols"]

    # Build feature row (same order as training)
    karat_map = {"14K": 14, "18K": 18, "22K": 22, "24K": 24, "22KT": 22}
    karat_num = karat_map.get(karat.upper(), 18)
    purity = karat_num / 24.0
    density = GOLD_DENSITIES_XGB.get(karat.upper(), 0.01558)
    product_type = _extract_product_type(product_name)
    complexity = _extract_complexity(product_name)
    word_count = len(product_name.split())
    has_diamond = 1 if diamond_carat > 0 else 0

    # Encode product_type — handle unseen labels gracefully
    try:
        pt_encoded = label_encoder.transform([product_type])[0]
    except ValueError:
        pt_encoded = 0  # fallback to first class

    row = pd.DataFrame([{
        "gold_weight_grams": gold_weight_grams,
        "diamond_carat": diamond_carat,
        "has_diamond": has_diamond,
        "karat_numeric": karat_num,
        "gold_purity_fraction": purity,
        "density_g_mm3": density,
        "design_complexity": complexity,
        "name_word_count": word_count,
        "image_count": image_count,
        "weight_x_purity": gold_weight_grams * purity,
        "weight_per_image": gold_weight_grams / max(image_count, 1),
        "product_type_encoded": pt_encoded,
    }])

    # Impute (no-op if no NaN, but keeps consistency)
    row_imputed = pd.DataFrame(imputer.transform(row), columns=feature_cols)

    # Predict
    volume_pred = float(model.predict(row_imputed)[0])

    return {
        "volume_mm3": volume_pred,
        "weight_14k": volume_pred * GOLD_DENSITIES_XGB["14K"],
        "weight_18k": volume_pred * GOLD_DENSITIES_XGB["18K"],
        "weight_22k": volume_pred * GOLD_DENSITIES_XGB["22K"],
        "model_metrics": artifact["metrics"],
    }


# ---------------------------------------------------------------------------
# Ensemble helper
# ---------------------------------------------------------------------------

def ensemble_volume(
    llm_volume: float,
    rag_volume: Optional[float],
    xgb_volume: Optional[float],
    llm_confidence: str = "medium",
) -> dict:
    """
    Weighted ensemble of LLM, RAG, and XGBoost volume estimates.

    Weights are adjusted based on LLM confidence and data availability:
    - high confidence LLM → LLM dominant (0.60 / 0.25 / 0.15)
    - medium confidence    → balanced    (0.45 / 0.35 / 0.20)
    - low confidence       → RAG/XGB dominant (0.30 / 0.40 / 0.30)
    """
    weight_profiles = {
        "high":   {"llm": 0.60, "rag": 0.25, "xgb": 0.15},
        "medium": {"llm": 0.45, "rag": 0.35, "xgb": 0.20},
        "low":    {"llm": 0.30, "rag": 0.40, "xgb": 0.30},
    }
    
    profile = weight_profiles.get(llm_confidence, weight_profiles["medium"])
    
    # Build available sources
    sources = {"llm": llm_volume}
    weights = {"llm": profile["llm"]}
    
    if rag_volume is not None and rag_volume > 0:
        sources["rag"] = rag_volume
        weights["rag"] = profile["rag"]
    
    if xgb_volume is not None and xgb_volume > 0:
        sources["xgb"] = xgb_volume
        weights["xgb"] = profile["xgb"]
    
    # Normalize weights
    total_w = sum(weights.values())
    for k in weights:
        weights[k] /= total_w
    
    # Weighted average
    ensemble_vol = sum(sources[k] * weights[k] for k in sources)
    
    return {
        "ensemble_volume_mm3": ensemble_vol,
        "sources": sources,
        "weights": weights,
        "profile_used": llm_confidence,
    }
