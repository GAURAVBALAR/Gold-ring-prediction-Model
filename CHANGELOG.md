# Changelog

Format: [YYYY-MM-DD] | [vX.X.X] | [Type: Added/Fixed/Changed/Removed]

---

## [Unreleased]
- [Work in progress]

---

## [0.2.0] — 2026-05-02

### Added
- **Volume-Based Prediction:** AI now predicts base volume (mm³) instead of weights directly. Backend handles karat conversion (14K, 18K, 22K) using standard densities.
- **Training Data Ingestion:** New endpoint and UI to upload verified ring designs (image + actual weight) to the training pool (RAG).
- **Weight Ranges:** Predictions now return a "Min-Max" range with a safety overestimation bias for manufacturing.
- **22K Support:** Added calculations and UI support for 22K Gold.

### Changed
- Refactored LLM prompt for Gemini 3 Flash Preview to prioritize RAG-based volume anchoring.
- Updated database schema to include volume and range fields.
- Admin Panel now includes a "Add Verified Training Design" form.

---

## [0.1.0] — 2026-05-02

### Added
- Project initialized
- Visual RAG with CLIP and Pinecone
- Gold weight prediction using Gemini 3 Flash Preview
