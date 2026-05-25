import pandas as pd
import os

# Paths
INPUT_CSV = "Tanishq_Jewelry_Dataset_Final/tanishq_jewelry_dataset.csv"
OUTPUT_CSV = "Tanishq_Jewelry_Dataset_Final/tanishq_jewelry_enriched.csv"
IMAGE_DIR_REAL = "Tanishq_Jewelry_Dataset_Final/images/"

def fix_path(path_str):
    if not path_str or pd.isna(path_str):
        return ""
    # The CSV has paths like 'output/tanishq_images/uncategorized/51m5c1faumaa002ea000001_1.jpg'
    # We need 'Tanishq_Jewelry_Dataset_Final/images/uncategorized/51m5c1faumaa002ea000001_1.jpg'
    parts = path_str.split('|')
    fixed_parts = []
    for p in parts:
        filename = os.path.basename(p)
        # Check if it's in uncategorized or rings (common Tanishq categories)
        # For now, we assume 'uncategorized' as seen in the file listing
        fixed_path = os.path.join(IMAGE_DIR_REAL, "uncategorized", filename)
        fixed_parts.append(fixed_path)
    return "|".join(fixed_parts)

def preprocess():
    print(f"Reading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    print("Fixing image paths...")
    df['local_image_paths'] = df['local_image_paths'].apply(fix_path)
    
    print("Adding geometric metadata placeholders...")
    # Add columns if they don't exist
    new_cols = [
        'ring_size', 'inner_diameter_mm', 'band_width_mm', 'band_thickness_mm',
        'center_stone_shape', 'center_stone_length_mm', 'center_stone_width_mm',
        'center_stone_ct', 'side_stone_count', 'side_stone_ct', 'estimated_volume_mm3'
    ]
    for col in new_cols:
        if col not in df.columns:
            df[col] = None

    # Fill center_stone_ct from diamond_weight_carats if applicable
    df['center_stone_ct'] = df['diamond_weight_carats']
    
    # Save the enriched CSV
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Enriched dataset saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    preprocess()
