"""
backend/app/api/xgboost_predictor.py  (NEW FILE)
=================================================
XGBoost inference wrapper. Loads the pre-trained model and provides
a predict() function for use in the ensemble.

The model is weak on its own (R² ≈ 0.18) because the dataset lacks
critical physical dimensions (band_width, stone_carat, etc.).
Its role in the ensemble is as a SANITY CHECKER, not a primary predictor.

When to trust the XGBoost output more:
  - ring_size is known (strongest tabular feature)
  - style is known
  - stone info is extractable from the product name

When to down-weight it:
  - ring_size missing
  - style unknown
  - LLM and RAG are in strong agreement
"""

import os
import re
import pickle
import numpy as np
from typing import Optional
from loguru import logger


_model = None
_meta = None

MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/xgboost_model.pkl")
META_PATH  = os.path.join(os.path.dirname(__file__), "../../models/feature_meta.pkl")


def _load():
    global _model, _meta
    if _model is None:
        try:
            with open(MODEL_PATH, "rb") as f:
                _model = pickle.load(f)
            with open(META_PATH, "rb") as f:
                _meta = pickle.load(f)
            logger.info("XGBoost model loaded successfully")
        except FileNotFoundError:
            logger.warning(
                "XGBoost model not found. Run train_xgboost.py first. "
                "Prediction will proceed without XGBoost."
            )
        except Exception as e:
            logger.error(f"Failed to load XGBoost model: {e}")


def predict_14k(
    ring_size: Optional[float],
    style: Optional[str],
    original_karat: int = 18,
    product_name: str = "",
    source: str = "unknown",
) -> Optional[float]:
    """
    Predict gold weight in 14K grams using XGBoost tabular features.
    Returns None if model not available.

    Note: All predictions are in 14K grams.
    Use GOLD_DENSITIES to convert to other karats in llm_utils.py.
    """
    _load()
    if _model is None:
        return None

    meta = _meta
    ring_size_to_diam = meta["ring_size_to_diam"]
    style_complexity  = meta["style_complexity"]
    known_stones      = meta["known_stones"]
    known_cuts        = meta["known_cuts"]

    # ── Feature extraction (must match train_xgboost.py exactly) ──────────
    try:
        name = product_name.lower()

        ring_size_val = float(ring_size) if ring_size else 7.0
        diam_keys = sorted(ring_size_to_diam.keys())
        closest = min(diam_keys, key=lambda s: abs(s - ring_size_val))
        inner_diam = ring_size_to_diam[closest]
        inner_circ = inner_diam * np.pi
        shank_proxy = inner_circ * 3.5 * 1.5

        style_val = style or "Unknown"
        style_complexity_val = style_complexity.get(style_val, 3)

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
        main_cut   = get_cut(name)

        # Label encoding — must match training (use index of sorted unique values)
        # Since we saved encoders per-feature, we use simple hashing fallback
        def simple_encode(val, known_list):
            vals = sorted(set(known_list + [val]))
            return vals.index(val) if val in vals else 0

        stone_list = known_stones + ["none"]
        cut_list   = known_cuts + ["none"]
        style_list = list(style_complexity.keys()) + ["Unknown"]
        source_list = ["angara", "orra", "rings_final", "tanishq", "unknown"]

        features = [
            ring_size_val,
            inner_diam,
            inner_circ,
            shank_proxy,
            float(original_karat),
            simple_encode(style_val, style_list),
            style_complexity_val,
            simple_encode(main_stone, stone_list),
            simple_encode(main_cut, cut_list),
            float(sum(1 for s in ["solitaire","halo","three-stone","cluster","bypass"] if s in name)),
            float(bool(re.search(r"(\d+(?:\.\d+)?)\s*ct", name))),
            float(bool(re.search(r"(\d+(?:\.\d+)?)\s*ct", name)) *
                  float(re.search(r"(\d+(?:\.\d+)?)\s*ct", name).group(1)
                        if re.search(r"(\d+(?:\.\d+)?)\s*ct", name) else 0)),
            simple_encode(source, source_list),
        ]

        # Trim/pad to expected number of features
        n_feats = len(meta["feature_names"])
        if len(features) > n_feats:
            features = features[:n_feats]
        elif len(features) < n_feats:
            features += [0.0] * (n_feats - len(features))

        X = np.array([features], dtype=np.float32)
        pred = float(_model.predict(X)[0])
        return max(pred, 0.1)  # safety floor

    except Exception as e:
        logger.error(f"XGBoost inference error: {e}")
        return None
