import os
import re
import pickle
from typing import Optional
from loguru import logger

# Try importing xgboost and numpy, handling ImportError gracefully
try:
    import numpy as np
    import xgboost as xgb
    _xgboost_available = True
except ImportError:
    logger.warning("xgboost or numpy is not installed. XGBoost inference will return None.")
    _xgboost_available = False

_model = None
_meta = None

# Model paths are relative to this file's directory
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/xgboost_model.pkl")
META_PATH  = os.path.join(os.path.dirname(__file__), "../../models/feature_meta.pkl")

def _load():
    """
    Lazy load both XGBoost model and feature metadata pickles.
    """
    global _model, _meta
    if not _xgboost_available:
        return
        
    if _model is None:
        try:
            if os.path.exists(MODEL_PATH) and os.path.exists(META_PATH):
                with open(MODEL_PATH, "rb") as f:
                    _model = pickle.load(f)
                with open(META_PATH, "rb") as f:
                    _meta = pickle.load(f)
                logger.info("XGBoost model and feature metadata loaded successfully.")
            else:
                logger.warning(
                    f"XGBoost model files not found at {MODEL_PATH}. "
                    "Inference will proceed with None (no XGBoost blend)."
                )
        except Exception as e:
            logger.error(f"Failed to load XGBoost model: {e}")
            _model = None
            _meta = None

def predict_14k(
    ring_size: Optional[float],
    style: Optional[str],
    original_karat: int = 18,
    product_name: str = "",
    source: str = "unknown"
) -> Optional[float]:
    """
    Predict gold weight in 14K grams using tabular features from the product design.
    Returns None if xgboost is not available, or model file is not found.
    """
    if not _xgboost_available:
        return None
        
    _load()
    if _model is None or _meta is None:
        return None

    try:
        meta = _meta
        ring_size_to_diam = meta["ring_size_to_diam"]
        style_complexity  = meta["style_complexity"]
        known_stones      = meta["known_stones"]
        known_cuts        = meta["known_cuts"]
        feature_names     = meta["feature_names"]

        # --- Feature Engineering (aligns 100% with train_xgboost.py) ---
        ring_size_val = float(ring_size) if ring_size is not None else 7.0
        
        # Handle ring size diameter mapping
        closest_size = min(ring_size_to_diam.keys(), key=lambda s: abs(s - ring_size_val))
        inner_diam = ring_size_to_diam[closest_size]
        inner_circ = inner_diam * np.pi
        shank_proxy = inner_circ * 3.5 * 1.5
        
        orig_karat = float(original_karat) if original_karat else 18.0
        
        style_val = style or "Unknown"
        style_complexity_val = style_complexity.get(style_val, 3)
        
        name = str(product_name).lower().strip()
        
        def get_stone(n):
            for s in known_stones:
                if s in n:
                    return s
            return "none"

        def get_cut(n):
            for c in known_cuts:
                if c in n:
                    return c
            return "none"

        main_stone = get_stone(name)
        main_cut = get_cut(name)
        
        # Encoders fallback matching simple label encoding
        def simple_encode(val, known_list):
            vals = sorted(set(known_list + [val]))
            return vals.index(val) if val in vals else 0
            
        stone_list = known_stones + ["none"]
        cut_list = known_cuts + ["none"]
        style_list = list(style_complexity.keys()) + ["Unknown"]
        source_list = ["angara", "orra", "rings_final", "tanishq", "unknown"]
        
        # Carat from name
        m_ct = re.search(r"(\d+(?:\.\d+)?)\s*ct", name)
        stone_ct_val = float(m_ct.group(1)) if m_ct else 0.0
        
        # Side stone count
        m_side = re.search(r"(\d+)\s*(?:side|accent|pave)\s*(?:stone|diamond)", name)
        side_stone_count_val = int(m_side.group(1)) if m_side else 0
        
        # Heavy setting
        heavy_stones = {"emerald", "oval", "cushion", "pear", "marquise"}
        has_heavy_setting = int(any(s in name for s in heavy_stones))
        
        # Binary flags
        is_pave = int(any(s in name for s in ["pave", "pavé"]))
        is_three_stone = int(any(s in name for s in ["three stone", "three-stone", "3 stone", "3-stone"]))
        has_side_diamonds = int(any(s in name for s in ["side diamond", "accent", "side stone"]))
        has_halo = int(style_val.lower() == "halo")
        is_eternity = int("eternity" in name)
        is_split_shank = int("split shank" in name)
        is_cathedral = int("cathedral" in name)
        is_bypass = int("bypass" in name)
        is_rose_gold = int("rose gold" in name)
        is_white_gold = int("white gold" in name)
        is_lab_grown = int(any(s in name for s in ["lab-grown", "lab grown"]))
        
        # Re-build feature array matching exact training sequence
        features = [
            # Physics / geometry
            ring_size_val, inner_diam, inner_circ, shank_proxy,
            # Material
            orig_karat,
            # Design complexity
            simple_encode(style_val, style_list), style_complexity_val,
            # Stone / setting
            simple_encode(main_stone, stone_list), simple_encode(main_cut, cut_list),
            stone_ct_val, float(side_stone_count_val),
            float(has_heavy_setting), float(is_pave), float(is_three_stone),
            float(has_side_diamonds), float(has_halo), float(is_eternity),
            float(is_split_shank), float(is_cathedral), float(is_bypass),
            # Metal / finish
            float(is_rose_gold), float(is_white_gold), float(is_lab_grown),
            # Source
            simple_encode(source, source_list)
        ]

        # Safety padding or trimming based on meta feature names list
        n_feats = len(feature_names)
        if len(features) > n_feats:
            features = features[:n_feats]
        elif len(features) < n_feats:
            features += [0.0] * (n_feats - len(features))

        X = np.array([features], dtype=np.float32)
        pred = float(_model.predict(X)[0])
        return max(pred, 0.1)  # safety floor weight
        
    except Exception as e:
        logger.error(f"XGBoost inference prediction failed: {e}")
        return None
