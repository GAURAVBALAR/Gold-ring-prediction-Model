"""
Gold Weight Prediction — XGBoost Training Pipeline
===================================================
Run this script to train the XGBoost model from master_dataset.csv.
Output: backend/models/xgboost_model.pkl + backend/models/feature_encoder.pkl

Usage:
    python train_xgboost.py
    python train_xgboost.py --csv path/to/custom.csv
"""

import pandas as pd
import numpy as np
import pickle
import os
import re
import argparse
import warnings
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")

# ─── Ring Size → Inner Diameter (mm) — Standard US Scale ────────────────────
RING_SIZE_TO_DIAM = {
    4: 14.8,  4.5: 15.3,  5: 15.7,  5.5: 16.1,
    6: 16.5,  6.5: 16.9,  7: 17.3,  7.5: 17.7,
    8: 18.2,  8.5: 18.6,  9: 19.0,  9.5: 19.4,
    10: 19.8, 10.5: 20.2, 11: 20.6, 12: 21.4,
}

# Ring style → approximate complexity / metal-volume multiplier
STYLE_COMPLEXITY = {
    "Cocktail": 5, "Cluster": 4, "Halo": 4, "Vintage": 4,
    "Engagement": 4, "Cathedral": 3, "Geometric": 3,
    "Solitaire": 3, "Eternity": 3, "Vanki": 3, "Floral": 3,
    "Band": 2, "Bezel": 2, "Bypass": 2, "Chevron": 2,
    "Promise": 2, "Infinity": 2, "Classic": 2,
    "Heart": 2, "Minimal": 1, "Unknown": 3,
}

# Stones that add significant prong/setting metal
HEAVY_SETTING_STONES = {"emerald", "oval", "cushion", "pear", "marquise"}

KNOWN_STONES = [
    "diamond", "emerald", "sapphire", "ruby", "tanzanite", "opal",
    "amethyst", "pearl", "moissanite", "morganite", "topaz", "garnet",
    "tourmaline", "aquamarine", "peridot", "spinel", "alexandrite",
    "citrine", "iolite",
]

KNOWN_CUTS = [
    "round", "oval", "cushion", "princess", "pear", "marquise",
    "emerald", "asscher", "radiant", "heart", "trillion",
]


# ─── Feature Engineering ────────────────────────────────────────────────────
def extract_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Build a richer feature set from the raw dataset columns.
    Returns (feature_df, feature_names).
    """
    d = df.copy()

    # 1. Ring geometry (physics-grounded)
    d["ring_size_us"] = pd.to_numeric(d["ring_size_us"], errors="coerce")
    d["ring_size_us"].fillna(d["ring_size_us"].median(), inplace=True)
    d["inner_diam_mm"] = d["ring_size_us"].map(RING_SIZE_TO_DIAM)
    d["inner_diam_mm"].fillna(d["inner_diam_mm"].median(), inplace=True)
    d["inner_circ_mm"] = d["inner_diam_mm"] * np.pi
    # Approximate shank band volume proxy (circumference × typical band area)
    d["shank_vol_proxy"] = d["inner_circ_mm"] * 3.5 * 1.5  # ~avg band 3.5mm × 1.5mm

    # 2. Karat
    d["original_karat"] = pd.to_numeric(d["original_karat"], errors="coerce").fillna(18)

    # 3. Style features
    d["style"] = d["style"].fillna("Unknown")
    d["style_complexity"] = d["style"].map(STYLE_COMPLEXITY).fillna(3)

    # 4. Source encoding
    source_enc = LabelEncoder()
    d["source_code"] = source_enc.fit_transform(d["source"].fillna("unknown"))

    # 5. Name-derived features
    names = d["product_name"].str.lower().fillna("")

    # Main gemstone
    def get_stone(n):
        for s in KNOWN_STONES:
            if s in n:
                return s
        return "none"

    def get_cut(n):
        for c in KNOWN_CUTS:
            if c in n:
                return c
        return "none"

    d["main_stone"] = names.apply(get_stone)
    d["main_cut"] = names.apply(get_cut)
    d["is_lab_grown"] = names.str.contains("lab-grown|lab grown").astype(int)
    d["is_rose_gold"] = names.str.contains("rose gold").astype(int)
    d["is_white_gold"] = names.str.contains("white gold").astype(int)
    d["is_three_stone"] = names.str.contains(r"three.stone|3.stone", regex=True).astype(int)
    d["is_pave"] = names.str.contains(r"pav[eé]|pavé").astype(int)
    d["is_split_shank"] = names.str.contains("split shank").astype(int)
    d["is_cathedral"] = names.str.contains("cathedral").astype(int)
    d["has_halo"] = (d["style"].str.lower() == "halo").astype(int)
    d["is_eternity"] = names.str.contains("eternity").astype(int)
    d["is_bypass"] = names.str.contains("bypass").astype(int)
    d["has_side_diamonds"] = names.str.contains(r"side.*diamond|diamond.*accent|accent", regex=True).astype(int)
    d["has_heavy_setting"] = names.apply(
        lambda n: int(any(s in n for s in HEAVY_SETTING_STONES))
    )

    # Carat from name (e.g. "1.5 ct", "2ct")
    def extract_ct(n):
        m = re.search(r"(\d+(?:\.\d+)?)\s*ct", n)
        return float(m.group(1)) if m else 0.0

    d["stone_ct_name"] = names.apply(extract_ct)

    # Number of side stones from name
    def extract_side_count(n):
        m = re.search(r"(\d+)\s*(?:side|accent|pave)\s*(?:stone|diamond)", n)
        return int(m.group(1)) if m else 0

    d["side_stone_count_name"] = names.apply(extract_side_count)

    # Label-encode categoricals
    for col in ["style", "main_stone", "main_cut"]:
        enc = LabelEncoder()
        d[f"{col}_code"] = enc.fit_transform(d[col])

    feature_cols = [
        # Physics / geometry
        "ring_size_us", "inner_diam_mm", "inner_circ_mm", "shank_vol_proxy",
        # Material
        "original_karat",
        # Design complexity
        "style_code", "style_complexity",
        # Stone / setting
        "main_stone_code", "main_cut_code",
        "stone_ct_name", "side_stone_count_name",
        "has_heavy_setting", "is_pave", "is_three_stone",
        "has_side_diamonds", "has_halo", "is_eternity",
        "is_split_shank", "is_cathedral", "is_bypass",
        # Metal / finish
        "is_rose_gold", "is_white_gold", "is_lab_grown",
        # Source
        "source_code",
    ]

    return d[feature_cols], feature_cols


# ─── Training ───────────────────────────────────────────────────────────────
def train(csv_path: str, output_dir: str = "./backend/models"):
    print(f"\n{'='*60}")
    print("  Gold Weight XGBoost Training Pipeline")
    print(f"{'='*60}\n")

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df):,} records from {csv_path}")

    X_df, feature_names = extract_features(df)
    y = df["gold_weight_14k"].values
    X = X_df.values

    # ── Outlier removal (IQR) ──
    q1, q3 = np.percentile(y, 25), np.percentile(y, 75)
    iqr = q3 - q1
    mask = (y >= q1 - 3 * iqr) & (y <= q3 + 3 * iqr)
    X, y = X[mask], y[mask]
    print(f"After outlier removal: {len(y):,} records ({(~mask).sum()} removed)")

    # ── Train / Test Split ──
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    # ── XGBoost Model ──
    model = XGBRegressor(
        n_estimators=600,
        max_depth=5,
        learning_rate=0.03,
        min_child_weight=10,
        subsample=0.8,
        colsample_bytree=0.75,
        reg_alpha=0.2,
        reg_lambda=1.5,
        gamma=0.1,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )

    # ── 5-Fold Cross Validation ──
    print("\nRunning 5-fold cross-validation...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    
    cv_mae = []
    cv_rmse = []
    cv_r2 = []
    
    for fold, (train_idx, val_idx) in enumerate(kf.split(X_train, y_train)):
        X_tr, X_val = X_train[train_idx], X_train[val_idx]
        y_tr, y_val = y_train[train_idx], y_train[val_idx]
        
        fold_model = XGBRegressor(
            n_estimators=600,
            max_depth=5,
            learning_rate=0.03,
            min_child_weight=10,
            subsample=0.8,
            colsample_bytree=0.75,
            reg_alpha=0.2,
            reg_lambda=1.5,
            gamma=0.1,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        fold_model.fit(X_tr, y_tr)
        val_preds = fold_model.predict(X_val)
        
        f_mae = mean_absolute_error(y_val, val_preds)
        f_rmse = np.sqrt(mean_squared_error(y_val, val_preds))
        f_r2 = r2_score(y_val, val_preds)
        
        cv_mae.append(f_mae)
        cv_rmse.append(f_rmse)
        cv_r2.append(f_r2)
        
        print(f"  Fold {fold+1} - MAE: {f_mae:.4f}g | RMSE: {f_rmse:.4f}g | R2: {f_r2:.4f}")
        
    cv_mae = np.array(cv_mae)
    cv_rmse = np.array(cv_rmse)
    cv_r2 = np.array(cv_r2)
    
    print(f"\nMean CV Results:")
    print(f"  CV MAE:  {cv_mae.mean():.4f}g +/- {cv_mae.std():.4f}")
    print(f"  CV RMSE: {cv_rmse.mean():.4f}g +/- {cv_rmse.std():.4f}")
    print(f"  CV R2:   {cv_r2.mean():.4f} +/- {cv_r2.std():.4f}")

    # ── Final Fit + Test Set Eval ──
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    errors = np.abs(preds - y_test)

    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)
    pct_10 = np.mean(errors / y_test < 0.10) * 100
    pct_15 = np.mean(errors / y_test < 0.15) * 100
    pct_20 = np.mean(errors / y_test < 0.20) * 100
    pct_03g = np.mean(errors < 0.30) * 100
    pct_05g = np.mean(errors < 0.50) * 100

    print(f"\nTest Set Results ({len(y_test):,} samples):")
    print(f"  MAE:            {mae:.4f}g")
    print(f"  RMSE:           {rmse:.4f}g")
    print(f"  R2:             {r2:.4f}")
    print(f"  Within +/-0.30g:  {pct_03g:.1f}%")
    print(f"  Within +/-0.50g:  {pct_05g:.1f}%")
    print(f"  Within 10%:     {pct_10:.1f}%")
    print(f"  Within 15%:     {pct_15:.1f}%")
    print(f"  Within 20%:     {pct_20:.1f}%")

    # ── Feature Importances ──
    print("\nTop Feature Importances:")
    importances = sorted(zip(feature_names, model.feature_importances_), key=lambda x: -x[1])
    for name, imp in importances[:12]:
        bar = "#" * int(imp * 60)
        print(f"  {name:<28} {imp:.4f}  {bar}")

    # ── Save Model ──
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, "xgboost_model.pkl")
    meta_path = os.path.join(output_dir, "feature_meta.pkl")

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    # Save feature engineering metadata for inference
    meta = {
        "feature_names": feature_names,
        "ring_size_to_diam": RING_SIZE_TO_DIAM,
        "style_complexity": STYLE_COMPLEXITY,
        "known_stones": KNOWN_STONES,
        "known_cuts": KNOWN_CUTS,
    }
    with open(meta_path, "wb") as f:
        pickle.dump(meta, f)

    print(f"\nSuccess: Model saved: {model_path}")
    print(f"Success: Meta saved:  {meta_path}")
    print(f"\nNOTE: This model provides the tabular anchor.")
    print("Combine with LLM visual estimate for best accuracy.")

    return model, feature_names


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="master_dataset.csv", help="Path to dataset CSV")
    parser.add_argument("--out", default="./backend/models", help="Output directory")
    args = parser.parse_args()
    train(args.csv, args.out)
