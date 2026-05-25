import sys
import os
import asyncio
import pandas as pd
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

# Setup path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from app.api.llm_utils import get_llm_prediction
from app.core.xgboost_inference import predict_volume, ensemble_volume
from app.db.chroma_client import get_vector_db
from app.core.embeddings import get_clip_encoder
from app.core.constants import GOLD_DENSITIES

async def evaluate(sample_size=5):
    print("=" * 60)
    print(f"Evaluating Ensemble Accuracy on {sample_size} Random Master Dataset Records")
    print("=" * 60)
    
    dataset_path = PROJECT_ROOT / "backend" / "data" / "tanishq_density_dataset.csv"
    if not dataset_path.exists():
        print(f"Dataset not found at {dataset_path}")
        return
        
    df = pd.read_csv(dataset_path)
    # Filter to only records where image exists
    valid_rows = []
    for idx, row in df.iterrows():
        rel_path = str(row['local_image_paths']).split('|')[0]
        filename = os.path.basename(rel_path)
        img_path = PROJECT_ROOT / "Tanishq_Jewelry_Dataset_Final" / "images" / "uncategorized" / filename
        if img_path.exists():
            valid_rows.append(idx)
            
    df = df.loc[valid_rows]
    sample_df = df.sample(n=sample_size, random_state=42)
    
    config = {
        "default_llm": "gemini",
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY")
    }
    
    results = []
    
    print("\nLoading Encoders and Vector DB...")
    clip = get_clip_encoder()
    vdb = get_vector_db()
    
    for i, (_, row) in enumerate(sample_df.iterrows()):
        print(f"\n[{i+1}/{sample_size}] Processing {row['product_id']} - {row['product_name'][:30]}...")
        rel_path = str(row['local_image_paths']).split('|')[0]
        filename = os.path.basename(rel_path)
        img_path = PROJECT_ROOT / "Tanishq_Jewelry_Dataset_Final" / "images" / "uncategorized" / filename
            
        with open(img_path, "rb") as f:
            img_bytes = f.read()
            
        params = {
            "ring_size": 7.0,
            "stone_ct": float(row['diamond_carat']) if pd.notna(row['diamond_carat']) else 0.0,
            "side_stone_count": 0,
            "karat": str(row['gold_karat_purity']),
            "product_name": str(row['product_name'])
        }
        
        actual_vol = float(row['design_volume_mm3'])
        
        # 1. RAG
        embedding = clip.get_image_embedding(img_bytes)
        similar = vdb.query_similar(embedding)
        
        # 2. LLM
        try:
            pred = await get_llm_prediction([img_bytes], params, config, similar)
            llm_vol = pred.get("estimated_volume_mm3", 0)
            llm_conf = pred.get("raw", {}).get("confidence", "medium")
        except Exception as e:
            print(f"  [!] LLM failed: {e}")
            continue
            
        # 3. XGBoost
        rag_volumes = [ex.get("actual_volume_mm3", 0) for ex in similar if ex.get("actual_volume_mm3")]
        rag_avg = sum(rag_volumes)/len(rag_volumes) if rag_volumes else None
        
        # Use LLM's predicted weight for 18K as base proxy for XGBoost
        xgb_res = predict_volume(
            gold_weight_grams=pred.get("predicted_weight_18k", row['gold_weight_grams']), 
            karat="18K",
            diamond_carat=params["stone_ct"],
            product_name=params["product_name"],
            image_count=len(str(row['local_image_paths']).split('|'))
        )
        xgb_vol = xgb_res["volume_mm3"] if xgb_res else None
        
        # 4. Ensemble
        ens = ensemble_volume(llm_vol, rag_avg, xgb_vol, llm_conf)
        final_vol = ens["ensemble_volume_mm3"]
        
        error_pct = abs(final_vol - actual_vol) / actual_vol * 100
        
        results.append({
            "ID": row['product_id'],
            "Actual_Vol": actual_vol,
            "LLM": llm_vol,
            "RAG": rag_avg,
            "XGB": xgb_vol,
            "Final": final_vol,
            "Error%": error_pct
        })
        
        print(f"  -> Actual: {actual_vol:.1f} mm³ | Final: {final_vol:.1f} mm³ | Error: {error_pct:.1f}%")
        
    res_df = pd.DataFrame(results)
    
    print("\n" + "=" * 60)
    print("FINAL ENSEMBLE EVALUATION RESULTS")
    print("=" * 60)
    
    # Format for printing
    pd.options.display.float_format = '{:.1f}'.format
    print(res_df.to_string(index=False))
    
    mape = res_df['Error%'].mean()
    mae = abs(res_df['Final'] - res_df['Actual_Vol']).mean()
    
    print("\n" + "-" * 60)
    print(f"Mean Absolute Percentage Error (MAPE): {mape:.2f}%")
    print(f"Mean Absolute Error (MAE): {mae:.2f} mm³")
    print("-" * 60)

if __name__ == "__main__":
    asyncio.run(evaluate(10))  # Test on 10 samples
