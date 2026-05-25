# AI Context — Gold Weight Prediction System

## Overview
- **Purpose**: AI-powered gold weight and volume prediction for jewelry designs using Visual RAG and multi-karat calculations.
- **Stack**: FastAPI (Python), React (Vite/TS), CLIP (Embeddings), Pinecone (Vector DB), SQLite (Metadata), Gemini 3 Flash Preview (LLM).
- **Status**: In Development (v0.2.0)
- **Version**: 0.2.0
- **Last Updated**: 2026-05-02

## Core Logic: Volume-First
To ensure consistency across different materials, the system follows a **Volume-First** approach:
1.  **AI Estimation:** The LLM analyzes the image and estimates the material **Volume (mm³)**.
2.  **Karat Conversion:** Backend applies standard densities to calculate weights:
    - 14K: 13.07 g/cm³
    - 18K: 15.58 g/cm³
    - 22K: 17.50 g/cm³
3.  **Safety Buffer:** The AI is biased towards overestimation to provide a "Safe Cap" for manufacturing.

## Key Components
| Component | File | Purpose |
|-----------|------|---------|
| Prediction Engine | `backend/app/api/llm_utils.py` | Volume estimation and density calculations. |
| RAG Retrieval | `backend/app/db/pinecone_client.py` | Visual similarity search for historical anchoring. |
| Ingestion API | `backend/app/api/endpoints.py` | Endpoint to add verified designs to training pool. |
| Admin Panel | `frontend/src/components/AdminPanel.tsx` | Settings and Training Data entry. |

## Next Steps
- [x] Volume-based prediction logic.
- [x] 22K support.
- [x] Verified data ingestion form.
- [ ] XGBoost training on tabular data (Phase 3).
- [ ] Exporting predictions to CSV.
