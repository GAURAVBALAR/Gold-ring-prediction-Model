"""
XGBoost Gold Weight Prediction Model - Phase 3 Training Pipeline
================================================================

Trains an XGBoost Regressor to predict design_volume_mm3 from the
available tabular features in the Tanishq dataset.  Because the dataset
lacks geometric measurements (ring_size, band_width, etc.), we engineer
proxy features from what IS available (karat, diamond_carat, price,
product_name text features) and use KNN imputation for any missing values.

The trained model is saved as a joblib artifact that the backend can
load at startup for ensemble predictions (LLM + RAG + XGBoost).

Usage:
    cd gold-prediction-master
    python -m backend.scripts.train_xgboost          # from project root
    # OR
    python backend/scripts/train_xgboost.py          # direct execution
"""

import os
import sys
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.impute import KNNImputer
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
import xgboost as xgb
import joblib

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # gold-prediction-master/
DATA_DIR = PROJECT_ROOT / "backend" / "data"
MODEL_DIR = DATA_DIR / "models"
DATASET_PATH = DATA_DIR / "tanishq_density_dataset.csv"

GOLD_DENSITIES = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930,
    "22KT": 0.01750,  # handle alternate label in dataset
}

# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

def extract_product_type(name: str) -> str:
    """Extract jewelry type from product name."""
    name_lower = name.lower()
    if "ring" in name_lower:
        if "men" in name_lower:
            return "ring_men"
        return "ring"
    elif "earring" in name_lower or "stud" in name_lower or "jhumka" in name_lower or "hoop" in name_lower:
        return "earring"
    elif "pendant" in name_lower:
        return "pendant"
    elif "necklace" in name_lower or "chain" in name_lower:
        return "necklace"
    elif "bracelet" in name_lower or "bangle" in name_lower:
        return "bracelet"
    else:
        return "other"


def extract_design_complexity(name: str) -> int:
    """Score design complexity from name keywords (0-4)."""
    name_lower = name.lower()
    complexity = 0
    
    # Simple designs
    simple_keywords = ["plain", "sleek", "minimal", "delicate", "simple", "slender"]
    # Complex designs
    complex_keywords = ["filigree", "sculpted", "ornate", "weave", "lattice",
                        "geometric", "vintage", "layered", "interlaced", "floral",
                        "cathedral", "halo", "cluster", "pave", "pavé"]
    
    for kw in simple_keywords:
        if kw in name_lower:
            complexity -= 1
    for kw in complex_keywords:
        if kw in name_lower:
            complexity += 1
    
    # Clamp to 0-4 range
    return max(0, min(4, complexity + 2))


def extract_word_count(name: str) -> int:
    """Word count in product name — longer names often indicate more complex designs."""
    return len(name.split())


def has_diamond(diamond_carat: float) -> int:
    """Binary flag: does the piece have diamonds?"""
    return 1 if diamond_carat > 0 else 0


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix from the dataset."""
    features = pd.DataFrame()
    
    # --- Numeric features ---
    features["gold_weight_grams"] = df["gold_weight_grams"].astype(float)
    features["diamond_carat"] = df["diamond_carat"].fillna(0).astype(float)
    features["has_diamond"] = features["diamond_carat"].apply(has_diamond)
    
    # --- Karat as numeric (gold purity fraction) ---
    karat_map = {"14K": 14, "18K": 18, "22K": 22, "24K": 24, "22KT": 22}
    features["karat_numeric"] = df["gold_karat_purity"].map(karat_map).fillna(18)
    features["gold_purity_fraction"] = features["karat_numeric"] / 24.0
    
    # --- Density for this karat ---
    features["density_g_mm3"] = df["gold_karat_purity"].map(GOLD_DENSITIES).fillna(0.01558)
    
    # --- Text-derived features ---
    features["product_type"] = df["product_name"].apply(extract_product_type)
    features["design_complexity"] = df["product_name"].apply(extract_design_complexity)
    features["name_word_count"] = df["product_name"].apply(extract_word_count)
    
    # --- Image count (number of product images = proxy for design detail) ---
    features["image_count"] = df["local_image_paths"].apply(
        lambda x: len(str(x).split("|")) if pd.notna(x) else 1
    )
    
    # --- Interaction features ---
    features["weight_x_purity"] = features["gold_weight_grams"] * features["gold_purity_fraction"]
    features["weight_per_image"] = features["gold_weight_grams"] / features["image_count"]
    
    # --- Encode categorical (product_type) ---
    le = LabelEncoder()
    features["product_type_encoded"] = le.fit_transform(features["product_type"])
    
    return features, le


# ---------------------------------------------------------------------------
# Training Pipeline
# ---------------------------------------------------------------------------

def train_model():
    """Main training function."""
    print("=" * 60)
    print("XGBoost Gold Weight Prediction - Training Pipeline")
    print("=" * 60)
    
    # 1. Load dataset
    if not DATASET_PATH.exists():
        print(f"ERROR: Dataset not found at {DATASET_PATH}")
        print("Run create_density_dataset.py first.")
        sys.exit(1)
    
    df = pd.read_csv(DATASET_PATH)
    print(f"\n[DATA] Loaded {len(df)} records from {DATASET_PATH.name}")
    print(f"   Columns: {list(df.columns)}")
    
    # 2. Remove duplicates and rows with missing target or gold weight
    df = df.drop_duplicates(subset=["product_id"])
    df = df.dropna(subset=["design_volume_mm3", "gold_weight_grams"])
    print(f"   After dedup and dropping NaNs: {len(df)} records")
    
    # 3. Target variable
    target = df["design_volume_mm3"].astype(float)
    print(f"\n[TARGET] Target (design_volume_mm3):")
    print(f"   Mean:   {target.mean():.2f} mm³")
    print(f"   Median: {target.median():.2f} mm³")
    print(f"   Std:    {target.std():.2f} mm³")
    print(f"   Range:  [{target.min():.2f}, {target.max():.2f}] mm³")
    
    # 4. Build features
    features, label_encoder = build_features(df)
    
    # Select numeric columns for training
    feature_cols = [
        "diamond_carat", "has_diamond",
        "karat_numeric", "gold_purity_fraction", "density_g_mm3",
        "design_complexity", "name_word_count", "image_count",
        "product_type_encoded"
    ]
    
    X = features[feature_cols].copy()
    y = target.values
    
    print(f"\n[FEATURES] Features ({len(feature_cols)}):")
    for col in feature_cols:
        non_null = X[col].notna().sum()
        print(f"   {col:30s}  non-null: {non_null}/{len(X)}  mean: {X[col].mean():.4f}")
    
    # 5. Impute missing values
    imputer = KNNImputer(n_neighbors=5)
    X_imputed = pd.DataFrame(imputer.fit_transform(X), columns=feature_cols)
    
    print(f"\n[IMPUTE] KNN imputation complete (k=5)")
    
    # 6. Train XGBoost with cross-validation
    print(f"\n[TRAIN] Training XGBoost Regressor...")
    
    xgb_params = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "tree_method": "hist",  # fast CPU training
        "verbosity": 0,
    }
    
    model = xgb.XGBRegressor(**xgb_params)
    
    # Cross-validation
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_mae = cross_val_score(model, X_imputed, y, cv=kf, scoring="neg_mean_absolute_error")
    cv_r2 = cross_val_score(model, X_imputed, y, cv=kf, scoring="r2")
    
    print(f"\n[CV] 5-Fold Cross-Validation Results:")
    print(f"   MAE:  {-cv_mae.mean():.2f} ± {cv_mae.std():.2f} mm³")
    print(f"   R²:   {cv_r2.mean():.4f} ± {cv_r2.std():.4f}")
    
    # 7. Train final model on all data
    model.fit(X_imputed, y)
    
    # Final training metrics
    y_pred = model.predict(X_imputed)
    train_mae = mean_absolute_error(y, y_pred)
    train_mape = mean_absolute_percentage_error(y, y_pred)
    train_r2 = r2_score(y, y_pred)
    
    print(f"\n[MODEL] Final Model (trained on all data):")
    print(f"   Train MAE:  {train_mae:.2f} mm³")
    print(f"   Train MAPE: {train_mape:.2%}")
    print(f"   Train R²:   {train_r2:.4f}")
    
    # 8. Feature importance
    importances = dict(zip(feature_cols, model.feature_importances_))
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n[IMPORTANCE] Feature Importance:")
    for feat, imp in sorted_imp:
        bar = "#" * int(imp * 50)
        print(f"   {feat:30s}  {imp:.4f}  {bar}")
    
    # 9. Save artifacts
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    model_path = MODEL_DIR / "xgboost_v1.joblib"
    joblib.dump({
        "model": model,
        "imputer": imputer,
        "label_encoder": label_encoder,
        "feature_cols": feature_cols,
        "params": xgb_params,
        "metrics": {
            "cv_mae_mean": float(-cv_mae.mean()),
            "cv_mae_std": float(cv_mae.std()),
            "cv_r2_mean": float(cv_r2.mean()),
            "cv_r2_std": float(cv_r2.std()),
            "train_mae": float(train_mae),
            "train_mape": float(train_mape),
            "train_r2": float(train_r2),
            "n_samples": int(len(y)),
        },
    }, model_path)
    
    print(f"\n[SAVE] Model saved to: {model_path}")
    print(f"   Size: {model_path.stat().st_size / 1024:.1f} KB")
    
    # 10. Quick sanity check: predict for a known sample
    print(f"\n[CHECK] Sanity Check (first 5 predictions vs actual):")
    for i in range(min(5, len(y))):
        actual = y[i]
        predicted = y_pred[i]
        error_pct = abs(actual - predicted) / actual * 100
        print(f"   #{i+1}: Actual={actual:.1f} mm³  Predicted={predicted:.1f} mm³  Error={error_pct:.1f}%")
    
    print(f"\n{'=' * 60}")
    print(f"Training complete! Model ready for ensemble predictions.")
    print(f"{'=' * 60}")
    
    return model


if __name__ == "__main__":
    train_model()
