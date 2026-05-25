# Tanishq Jewelry Dataset (2026)

## Overview
This dataset contains high-quality structured data and images for **507 Tanishq products** (primarily rings, bands, and solitaires). It was generated using a custom-built Firecrawl scraper and cleaned for AI/ML training readiness.

## File Structure
- `tanishq_jewelry_dataset.csv`: The primary data file.
- `images/`: Folder containing product images organized by category.
  - Subfolders are named by product category (e.g., `rings`, `uncategorized`).
  - Image filenames follow the pattern: `{product_id}_{image_index}.jpg`.

## CSV Data Fields
- `product_name`: Full marketing name of the product.
- `product_id`: Unique SKU/ID from Tanishq.
- `gold_weight_grams`: Numerical gold weight in grams.
- `gold_karat_purity`: Standardized purity (e.g., 18K, 22K).
- `metal_color`: Primary metal color (yellow, rose, white).
- `total_price_inr`: Current listing price in Indian Rupees.
- `diamond_weight_carats`: Total diamond weight (if applicable).
- `stone_type`: Categorization of stones (diamond, gemstone, none).
- `image_urls`: Original source URLs for images.
- `local_image_paths`: Pipe-separated (`|`) relative paths to the locally saved images for direct mapping.
- `url`: Original Tanishq product page URL.

## Potential Use Cases
1. **Price Estimation Models**: Predicting jewelry prices based on metal weight and stone type.
2. **Computer Vision**: Training classifiers for jewelry styles or stone setting detection.
3. **Recommendation Engines**: Using text and image features for product similarity.

---
*Dataset generated on 2026-05-01*
