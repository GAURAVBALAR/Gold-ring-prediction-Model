import pandas as pd
import os

try:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
    from app.core.constants import GOLD_DENSITIES
except ImportError:
    GOLD_DENSITIES = {
        "14K": 0.01307,
        "18K": 0.01558,
        "22K": 0.01750,
        "24K": 0.01930
    }

def create_density_dataset(input_csv, output_csv):
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    print(f"Reading {input_csv}...")
    df = pd.read_csv(input_csv)
    
    # Check if necessary columns exist
    required_cols = ['gold_weight_grams', 'gold_karat_purity', 'product_name', 'product_id', 'local_image_paths']
    for col in required_cols:
        if col not in df.columns:
            print(f"Error: Missing required column {col}")
            return

    print("Calculating design volumes (density-based)...")
    
    def calculate_volume(row):
        karat = str(row['gold_karat_purity']).upper().strip()
        weight = float(row['gold_weight_grams'])
        
        # Default to 18K if unknown
        density = GOLD_DENSITIES.get(karat, GOLD_DENSITIES["18K"])
        return weight / density

    # Create new volume column
    df['design_volume_mm3'] = df.apply(calculate_volume, axis=1)
    
    # Add diamond carat if available
    if 'diamond_weight_carats' in df.columns:
        df['diamond_carat'] = df['diamond_weight_carats'].fillna(0.0)
    else:
        df['diamond_carat'] = 0.0

    # Select only the columns needed for the new RAG
    # This keeps the dataset lean
    new_df = df[[
        'product_id', 
        'product_name', 
        'gold_karat_purity', 
        'gold_weight_grams', 
        'design_volume_mm3', 
        'diamond_carat',
        'local_image_paths'
    ]]

    print(f"Saving to {output_csv}...")
    new_df.to_csv(output_csv, index=False)
    print("Done! New density-based dataset created.")

if __name__ == "__main__":
    input_path = "./Tanishq_Jewelry_Dataset_Final/tanishq_jewelry_dataset.csv"
    output_path = "./backend/data/tanishq_density_dataset.csv"
    
    os.makedirs("./backend/data", exist_ok=True)
    create_density_dataset(input_path, output_path)
