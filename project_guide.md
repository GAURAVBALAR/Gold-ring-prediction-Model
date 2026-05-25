# Gold Weight Prediction System — Project Guide

**Version:** 1.0  
**Author:** Priince Gondaliya  
**Domain:** Jewelry Manufacturing / AI-ML Engineering  
**Status:** Architecture Design Phase

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Why This Problem Matters](#2-why-this-problem-matters)
3. [Dataset Overview](#3-dataset-overview)
4. [Solution Architecture](#4-solution-architecture)
5. [Component Deep Dive](#5-component-deep-dive)
6. [The Feedback Loop — How the System Learns](#6-the-feedback-loop)
7. [Tech Stack](#7-tech-stack)
8. [Phase-by-Phase Implementation Plan](#8-phase-by-phase-implementation-plan)
9. [Failure Modes and How to Prevent Them](#9-failure-modes)
10. [Future: From 500 to 5000 Samples — The ML Upgrade Path](#10-future-upgrade-path)
11. [Glossary](#11-glossary)

---

## 1. Problem Statement

### 1.1 What Is the Problem?

In a jewelry manufacturing workshop, every ring design requires a precise estimate of how much gold will be needed before the piece is cast. This estimate drives:

- Raw material procurement (how many grams to melt)
- Job costing and profit margin calculation
- Customer pricing quotes
- Inventory planning for gold stock

Currently, this estimate is done **manually** — an experienced jeweler looks at a ring specification sheet (or CAD image), reads the parameters like ring size, stone dimensions, band width, and number of side stones, and uses years of experience to estimate the gold weight in grams.

This approach has three critical problems:

**Problem 1 — Human Error and Inconsistency**  
Different jewelers give different estimates for the same ring. A senior jeweler may estimate 2.4g while a junior one estimates 2.9g for an identical piece. This inconsistency causes financial leakage — either the workshop over-purchases gold (wastage cost) or under-purchases (production delay cost).

**Problem 2 — Speed Bottleneck**  
When a customer requests a quote, the jeweler must stop active work to manually calculate or estimate. For workshops handling 30–50 quote requests per day, this is a significant time cost.

**Problem 3 — No Improvement Over Time**  
Traditional estimation doesn't learn. A jeweler retiring takes their calibration with them. Past jobs — completed pieces with known actual gold usage — are rarely used to improve future estimates. Institutional knowledge is trapped in people, not systems.

### 1.2 Exact Scope of This Project

This project solves the following specific task:

> Given an image of a ring design and its manufacturing parameters (ring size, stone dimensions, band measurements, side stone count), predict the weight of gold required in grams — for both 14-karat and 18-karat yellow gold — with three-decimal precision (e.g., 2.188g).

This is a **regression problem** with a **multimodal input** (image + structured tabular data) and a **continuous numeric output** (gold weight in grams).

---

## 2. Why This Problem Matters

### 2.1 Business Impact

A workshop producing 20 rings per week with an average gold weight of 3g per ring at ₹6,000 per gram handles approximately ₹3,60,000 worth of gold weekly. A systematic estimation error of just 5% means ₹18,000 in weekly losses or surplus. Over a year, that is ₹9,36,000 — nearly ₹10 lakh — from a problem that is entirely preventable with better tooling.

### 2.2 Technical Opportunity

This problem sits at the intersection of computer vision, structured data modeling, and continual learning. It is an ideal candidate for a hybrid AI system because:

- The physics of the problem (geometry, density, volume) is well-understood and can guide the model
- Visual information (ring style, prong design, gallery structure) is available but hard to parameterize manually
- Historical job data (completed rings with actual gold used) is a natural feedback signal
- The system can get smarter with every verified prediction, without retraining from scratch

---

## 3. Dataset Overview

### 3.1 What Your 500-Sample Dataset Contains

Each record in the dataset represents one completed ring job. A record has the following fields:

**Visual Input**
- Ring image (top-down view, side view, or both)
- Image resolution: typically 800×800 to 1500×1500 pixels
- Format: JPG or PNG

**Structured Parameters (Tabular)**
- Ring size (USA scale, e.g., 6.50)
- Inner diameter in millimeters (derived from ring size via standard chart)
- Band width in millimeters
- Band thickness in millimeters
- Center stone shape (oval, round, cushion, princess, etc.)
- Center stone length × width in millimeters
- Center stone weight in carats
- Number of side stones
- Side stone total weight in carats
- Side stone sieve sizes (e.g., (+)00, (+)0)

**Target Variable (Label)**
- Actual gold weight used in grams (14k or 18k)
- Source: post-casting measurement, considered ground truth

### 3.2 Dataset Quality Assessment

| Metric | Status | Notes |
|--------|--------|-------|
| Sample count | 500 | Sufficient for XGBoost, borderline for fine-tuned vision models |
| Label quality | High | Post-casting measurement is accurate ground truth |
| Feature completeness | Medium | Band width and thickness often missing, must be imputed |
| Image quality | Variable | Render images are clean; workshop photos may have noise |
| Class balance | Unknown | Needs analysis — distribution of ring sizes and styles |

### 3.3 What 500 Samples Can and Cannot Do

**Can do:**
- Train a high-accuracy XGBoost regression model on tabular features alone (R² > 0.90 expected)
- Generate CLIP embeddings from images for retrieval (no training required, CLIP is pretrained)
- Power a vector database with 500 reference points for similarity search
- Serve as few-shot examples for LLM-based prediction

**Cannot do:**
- Train a reliable convolutional neural network from scratch (needs 5,000+ for this domain)
- Fine-tune a vision transformer like ResNet or ViT (needs 2,000+ minimum)
- Support a separate model per ring style or stone type (too few samples per subgroup)

---

## 4. Solution Architecture

### 4.1 System Overview

The system uses three cooperating components that produce a single prediction. No single component is trusted alone. The three components are:

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT LAYER                              │
│  Ring Image + Parameters (size, dims, CT, side stones)         │
└─────────────────────┬───────────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│  CLIP Encoder   │     │  Feature Vector  │
│  (image → 512d  │     │  (ring size,     │
│   embedding)    │     │  dims, CT, etc.) │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         ▼                       │
┌─────────────────┐              │
│  Vector DB      │              │
│  (Chroma /      │◄─────────────┘
│  Pinecone)      │   (also stores embeddings
│                 │    with tabular params)
└────────┬────────┘
         │
         │  Top-5 most similar past rings retrieved
         │  with their actual gold weights
         │
         ▼
┌──────────────────────────────────────────────────────┐
│                    LLM (Claude / GPT-4o)             │
│                                                      │
│  Receives:                                           │
│  - Input ring image                                  │
│  - Input parameters                                  │
│  - 5 retrieved similar rings (few-shot context)      │
│  - Geometric calculation rules (density, volume)     │
│                                                      │
│  Produces: LLM prediction (gold weight in grams)    │
└─────────────────────┬────────────────────────────────┘
                      │
                      │                    ┌───────────────────┐
                      │                    │  XGBoost Model    │
                      │                    │  (trained on 500  │
                      │◄───────────────────│  tabular records) │
                      │                    │                   │
                      │                    │  Produces: ML     │
                      │                    │  prediction       │
                      │                    └───────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ENSEMBLE LAYER                              │
│                                                                 │
│  Final prediction = (0.5 × LLM) + (0.5 × XGBoost)            │
│  Or: weighted by confidence score of each component            │
│                                                                 │
│  Confidence flags:                                             │
│  - HIGH: both predictions within 0.2g of each other           │
│  - MEDIUM: difference 0.2g–0.5g                               │
│  - LOW: difference > 0.5g → flag for human review             │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT + FEEDBACK LAYER                      │
│                                                                 │
│  Jeweler sees prediction → Approves or Corrects               │
│  After casting → Actual gold used is recorded                  │
│  Verified entry → Added to Vector DB + incremental XGBoost    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Why Three Components Instead of One

Each component covers a different type of knowledge:

| Component | Type of Knowledge | Strength | Weakness |
|-----------|-------------------|----------|----------|
| XGBoost | Statistical patterns in tabular features | Fast, accurate on structured input | Blind to visual ring style |
| CLIP + Vector DB | Visual similarity to known rings | Finds visually identical designs | Not a predictor, only a retriever |
| LLM | Physics, geometry, reasoning | Handles edge cases, explains its work | Expensive, slower, can drift |

Together they cover each other's blind spots. XGBoost is fast and accurate on parameters it has seen. CLIP retrieval gives the LLM real-world anchors instead of guessing. The LLM handles unusual designs that fall outside XGBoost's training distribution.

---

## 5. Component Deep Dive

### 5.1 CLIP Encoder (Image Embedding)

**What CLIP is:**  
CLIP (Contrastive Language-Image Pretraining) is a model trained by OpenAI on 400 million image-text pairs. It maps images into a 512-dimensional vector space where visually similar images land near each other. Crucially, it requires no training on your data — it works out of the box.

**How it is used here:**  
Every ring image in your dataset is passed through CLIP to produce a 512-dimensional embedding vector. This vector is stored in the vector database alongside the ring's parameters and actual gold weight.

When a new ring arrives, its image is embedded using the same CLIP encoder. The vector database is queried for the 5 closest vectors using cosine similarity. These 5 most similar past rings are retrieved — including their parameters and actual gold weights — and passed as context to the LLM.

**Why this matters:**  
Without CLIP, the LLM receives only the input parameters and must reason from scratch. With CLIP retrieval, the LLM receives 5 real examples of visually similar rings that were actually cast. This transforms the LLM's task from "calculate blindly" to "adjust from known reference points" — a fundamentally more accurate operation.

**Key implementation detail:**  
The embedding is generated from the ring image only, not the parameters. Parameters are stored as metadata alongside the embedding but are not mixed into the vector. This keeps the similarity search visually meaningful.

### 5.2 Vector Database (Chroma or Pinecone)

**What it stores:**  
Each record in the vector database contains:
- The 512-dimensional CLIP embedding (the search key)
- Ring parameters (ring size, stone dims, band dims, CT) as metadata
- Actual gold weight in grams (14k and 18k) as metadata
- Confidence tag (verified by jeweler or unverified)
- Timestamp and job ID

**How retrieval works:**  
Given a query embedding, the database returns the top-K records by cosine similarity. K=5 is the default — enough to show pattern without overloading the LLM context.

**Why Chroma for local, Pinecone for cloud:**  
Chroma is an open-source vector database that runs locally with zero infrastructure cost. It is ideal for the early phase. Pinecone is a managed cloud vector database that scales to millions of vectors and supports real-time indexing. The switch from Chroma to Pinecone is a one-line configuration change in the codebase.

**Growing the database:**  
Every verified prediction (approved by the jeweler after casting) is added to the vector database. The database never needs to be rebuilt — new records are inserted in real time. This is the core mechanism by which the system improves without retraining.

### 5.3 LLM Predictor (Claude / GPT-4o Vision)

**Input to the LLM:**  
The LLM receives a structured prompt containing:
1. The input ring image (as a base64-encoded vision input)
2. The input ring parameters
3. The 5 retrieved similar rings with their parameters and actual gold weights
4. The geometric calculation rules (volume formulas, gold densities for 14k and 18k)
5. Instructions to output structured JSON with the prediction and confidence level

**What the LLM does:**  
The LLM performs geometric reasoning — calculating volume of each ring component (shank, head, prongs, gallery, side stone settings), converting to grams using gold density, and adjusting its estimate based on the retrieved reference rings. The retrieved examples act as calibration points: if 3 visually similar rings of size 6.50 averaged 2.3g in 14k gold, the LLM uses that as an anchor.

**Output format:**  
```json
{
  "gold14k_g": 2.188,
  "gold18k_g": 2.609,
  "totalVolume_mm3": 167.432,
  "components": [...],
  "assumptions": [...],
  "confidence": "high",
  "confidenceNote": "Band dims provided; 5 similar rings retrieved from database"
}
```

**When the LLM is not called:**  
To reduce cost and latency, the LLM can be skipped when XGBoost confidence is high AND at least 3 retrieved similar rings are within 0.1g of each other. In this case, the system averages the top-3 retrieved weights directly. This is the fast path for common, well-documented ring designs.

### 5.4 XGBoost Regression Model

**Input features:**  
The XGBoost model is trained on the following features extracted from the 500-record dataset:

| Feature | Type | Notes |
|---------|------|-------|
| inner_diameter_mm | Float | Derived from ring size via lookup table |
| band_width_mm | Float | May be imputed with median if missing |
| band_thickness_mm | Float | May be imputed with median if missing |
| stone_length_mm | Float | Center stone |
| stone_width_mm | Float | Center stone |
| stone_ct | Float | Center stone carats |
| side_stone_count | Integer | Total number of side stones |
| side_stone_ct | Float | Total side stone carats |
| stone_shape_encoded | Integer | Label-encoded: oval=0, round=1, etc. |

**Target:**  
`gold_weight_grams` — actual post-casting measurement

**Why XGBoost over deep learning at 500 samples:**  
XGBoost is a gradient-boosted decision tree ensemble. It excels on tabular data with fewer than 10,000 samples. At 500 samples, a neural network would overfit severely — it would memorize the training set rather than learn generalizable patterns. XGBoost with cross-validation and careful hyperparameter tuning is the empirically correct choice at this scale.

**Incremental updates:**  
XGBoost does not natively support online learning (adding one new sample and updating the model). The workaround is batch incremental updates: every time 20 new verified records are added to the database, the XGBoost model is retrained from scratch on all verified data. Since training takes under 5 seconds at this scale, this is not a bottleneck. The model is serialized to disk and loaded into memory at prediction time.

### 5.5 Ensemble Layer

**How predictions are combined:**  
By default, the final prediction is the weighted average of the LLM prediction and the XGBoost prediction. The weights are dynamic based on confidence signals:

```
If XGBoost cross-validation RMSE < 0.15g:
  weight_xgboost = 0.6, weight_llm = 0.4

If LLM retrieved 5 similar rings with avg similarity > 0.90:
  weight_llm = 0.6, weight_xgboost = 0.4

Otherwise:
  weight_xgboost = 0.5, weight_llm = 0.5
```

**Disagreement threshold:**  
If the LLM prediction and XGBoost prediction differ by more than 0.5g, the system does not average them. Instead, it flags the prediction as LOW confidence and surfaces both predictions to the jeweler for manual adjudication. This prevents a bad prediction from silently entering the system.

---

## 6. The Feedback Loop — How the System Learns

### 6.1 The Core Problem with Self-Improving Systems

Most proposed "self-learning" AI systems have a fatal flaw: they use the model's own output as training data. If the model is wrong, it trains on wrong data, becomes more confidently wrong, and the error compounds over time. This is called model drift.

This system avoids that flaw by requiring a human verification signal before any prediction is added to the training dataset.

### 6.2 The Feedback Signal

There are two acceptable sources of ground truth in this system:

**Source 1 — Post-casting measurement (strongest)**  
After a ring is cast, the jeweler weighs the gold actually used. This measurement is the most reliable ground truth. The system stores the predicted weight alongside the actual weight, calculates the error, and if the error is below a threshold (default: ±0.3g), the record is flagged as verified and added to the vector database and XGBoost training pool.

**Source 2 — Jeweler manual correction (acceptable)**  
Before casting, the jeweler reviews the prediction. If they believe it is wrong based on experience, they can enter a corrected value. This corrected value is treated as ground truth. The original prediction and the correction are both stored for error analysis.

**What is never used as ground truth:**  
The system's own confidence score is never used to auto-approve predictions. A HIGH confidence prediction that has not been verified by a human does not enter the training pool. This is non-negotiable.

### 6.3 The Feedback Loop Step by Step

```
Step 1: New ring arrives → system predicts gold weight
Step 2: Jeweler reviews prediction (takes < 10 seconds)
Step 3a: Jeweler approves → prediction goes to casting queue
Step 3b: Jeweler corrects → corrected value stored, prediction discarded
Step 4: Ring is cast → actual gold weight measured and recorded
Step 5: Actual vs predicted gap is calculated
Step 6: If gap < 0.3g → record added to Vector DB and verified pool
Step 7: If verified pool has grown by 20 records → XGBoost retrained
Step 8: New embeddings generated from verified record's image → added to Vector DB
```

### 6.4 Why This Is Not Reinforcement Learning

The term "reinforcement learning" implies an agent that takes actions, receives rewards, and updates a policy. That is not what this system does. What this system does is called **continual learning with human-in-the-loop feedback** — a simpler, more reliable, and production-proven pattern. The distinction matters because:

- True RL requires a reward function that can be computed automatically. Our reward (actual gold weight) is only known after physical casting — a process that takes hours.
- RL agents can explore unpredictably in production environments. Our system makes one conservative prediction per ring, always.
- Human-in-the-loop continual learning is deployed in production at scale by companies like Google (Smart Reply), Spotify (playlist curation), and Duolingo (difficulty adjustment). RL is mostly used in games and robotics.

---

## 7. Tech Stack

### 7.1 Backend

| Component | Technology | Why |
|-----------|------------|-----|
| API server | FastAPI (Python) | Fast, async, automatic OpenAPI docs |
| ML model | XGBoost (scikit-learn API) | Best-in-class tabular regression |
| Image embedding | CLIP via OpenAI or Hugging Face | No training needed, robust visual features |
| Vector database | ChromaDB (local) → Pinecone (cloud) | Easy migration path, same API |
| LLM | Claude claude-sonnet-4-20250514 or GPT-4o | Vision support + structured JSON output |
| Model serialization | joblib | Industry standard for sklearn/XGBoost |
| Data storage | SQLite (local) → PostgreSQL (cloud) | Simple migration, same ORM |
| ORM | SQLAlchemy | Database-agnostic |

### 7.2 Frontend

| Component | Technology | Why |
|-----------|------------|-----|
| Framework | React | Component reusability, ecosystem |
| Styling | Tailwind CSS | Rapid UI development |
| State management | Zustand | Lightweight, no boilerplate |
| Charts | Recharts | Simple integration with React |
| Image upload | React Dropzone | Drag-and-drop support |

### 7.3 Infrastructure

| Component | Technology | Why |
|-----------|------------|-----|
| Containerization | Docker + Docker Compose | Reproducible environment |
| Model storage | Local filesystem → AWS S3 | Versioned model artifacts |
| Deployment | Railway or Render (early) → AWS EC2 (scale) | Cost-effective progression |
| Monitoring | Loguru (logging) + custom dashboard | Track prediction error over time |

### 7.4 Python Package List

```
# Core ML
xgboost==2.0.3
scikit-learn==1.4.0
numpy==1.26.4
pandas==2.2.0
joblib==1.3.2

# Image embedding
torch==2.2.0
open-clip-torch==2.24.0
Pillow==10.2.0

# Vector database
chromadb==0.4.22

# API
fastapi==0.110.0
uvicorn==0.27.0
python-multipart==0.0.9

# LLM client
anthropic==0.21.3

# Data validation
pydantic==2.6.0

# Utilities
python-dotenv==1.0.1
loguru==0.7.2
```

---

## 8. Phase-by-Phase Implementation Plan

### Phase 1 — Foundation (Weeks 1–2)

**Goal:** Working calculator with AI prediction, persistent history, no ML model yet.

Tasks:
- Build FastAPI backend with `/predict` endpoint that calls Claude API with geometric prompt
- Build React frontend with parameter input form and image upload
- Implement SQLite storage for prediction history
- Deploy locally with Docker Compose

Deliverable: Jewelers can request predictions and results are saved. Baseline dataset begins growing.

**Success metric:** 10 predictions per day logged with < 5 second response time.

### Phase 2 — Vector Database (Weeks 3–4)

**Goal:** CLIP embeddings + Chroma vector DB live. Retrieval-augmented LLM predictions.

Tasks:
- Run CLIP encoder on all 500 existing images → store embeddings in Chroma
- Modify `/predict` endpoint to query top-5 similar rings before calling LLM
- Include retrieved examples in LLM prompt as few-shot context
- Add confidence scoring based on retrieval similarity

Deliverable: LLM predictions are anchored to real historical examples. Confidence scores visible in UI.

**Success metric:** Retrieved rings are visually similar (manual spot-check by jeweler). LLM prediction error decreases compared to Phase 1 baseline.

### Phase 3 — XGBoost Model (Weeks 5–6)

**Goal:** First ML model trained and serving predictions in parallel with LLM.

Tasks:
- Clean and preprocess 500-record dataset (impute missing band dims, encode categorical features)
- Train XGBoost with 5-fold cross-validation
- Evaluate RMSE on held-out test set (target: RMSE < 0.20g)
- Add XGBoost `/predict-ml` endpoint
- Implement ensemble in main `/predict` endpoint

Deliverable: Both XGBoost and LLM predictions shown side by side in UI. Ensemble final result displayed.

**Success metric:** XGBoost RMSE < 0.25g on test set. Ensemble RMSE < 0.20g.

### Phase 4 — Feedback Loop (Weeks 7–8)

**Goal:** Jeweler verification UI. Verified records automatically update Vector DB and XGBoost.

Tasks:
- Build verification screen in frontend (approve / correct / pending casting)
- Build post-casting entry form (actual gold weight input)
- Implement auto-add to Chroma when gap < 0.3g
- Implement XGBoost batch retrain trigger (every 20 new verified records)
- Build prediction error dashboard (avg error per ring size, error trend over time)

Deliverable: System is fully self-improving with human oversight. Dataset grows automatically.

**Success metric:** 50 verified records added within 2 weeks of Phase 4 launch.

### Phase 5 — Optimization and Scale (Weeks 9–12)

**Goal:** Production-ready. Cost optimization. Migration to cloud.

Tasks:
- Implement fast path (skip LLM when XGBoost confidence high + 3 close retrievals)
- Migrate Chroma → Pinecone (if multi-device access needed)
- Migrate SQLite → PostgreSQL
- Add user authentication (workshop login)
- Deploy to cloud (Railway or Render)
- Build model versioning (track which XGBoost version made which prediction)

Deliverable: Workshop team using the tool daily. LLM called only ~30% of the time (cost reduction).

**Success metric:** Prediction error < 0.15g average across all ring sizes. LLM API cost < ₹500/month.

---

## 9. Failure Modes and How to Prevent Them

### 9.1 Model Drift via Self-Validation

**Risk:** If unverified predictions are added to training data, wrong predictions train the model to be more confidently wrong.

**Prevention:** Hard rule — only post-casting measurements or jeweler-corrected values are added to the verified pool. The system has no mechanism to auto-approve its own predictions.

### 9.2 Distribution Shift

**Risk:** A new ring style that looks nothing like the 500 training examples causes both XGBoost and CLIP retrieval to fail silently.

**Prevention:** The disagreement threshold. If XGBoost and LLM predictions differ by > 0.5g, the system flags it as LOW confidence and alerts the jeweler. This catches out-of-distribution inputs before they cause production errors.

### 9.3 CLIP Retrieval Returning Wrong Similar Rings

**Risk:** Two rings may look visually similar to CLIP but have very different gold weights (e.g., same band style but very different stone sizes).

**Prevention:** Similarity is scored on image embedding (visual similarity), but the metadata filter also checks that retrieved rings are within ±1.00 ring size of the query. This prevents a size-5 ring from being used as reference for a size-9 ring, even if they look identical in top-down view.

### 9.4 XGBoost Overfitting on Small Dataset

**Risk:** At 500 samples, XGBoost can overfit if tree depth and number of estimators are not regularized.

**Prevention:** Enforce cross-validated hyperparameter search with `max_depth` ≤ 5, `min_child_weight` ≥ 10, `subsample` = 0.8, `colsample_bytree` = 0.8. Evaluate on a held-out test set that is never used during tuning. Target RMSE on test set must match cross-validation RMSE within 0.05g — if they diverge, the model is overfitting.

### 9.5 LLM API Downtime

**Risk:** Claude or GPT-4o API is unavailable during business hours. Jewelers cannot get predictions.

**Prevention:** The LLM is not the only prediction path. If the LLM API call fails, the system falls back to XGBoost + top-3 retrieved weights average. This fallback is always available locally with no external dependency.

---

## 10. Future Upgrade Path

### 10.1 When to Upgrade from XGBoost to a Neural Model

The XGBoost model should be replaced with a multimodal neural network when the verified dataset crosses 3,000 records. At that point, a model like the following becomes viable:

```
Architecture:
  - Image branch: CLIP ViT-L/14 frozen encoder → 2 linear layers (fine-tuned)
  - Tabular branch: 3-layer MLP on ring parameters
  - Fusion: concatenate both branches → 2 shared layers → regression head
  - Output: gold weight in grams (single float)
  - Loss: Huber loss (robust to outlier measurements)
```

This architecture directly learns from images rather than using CLIP as a retrieval tool. It will outperform XGBoost + retrieval on diverse and edge-case ring designs — but only after sufficient training data is available.

### 10.2 When to Remove the LLM from the Prediction Path

The LLM is expensive and slow relative to a trained model. Once the neural model achieves RMSE < 0.10g on a held-out test set, the LLM's role shifts from predictor to explainer: it is no longer called for every prediction, only invoked when the ML model confidence is below threshold or when the jeweler requests a detailed breakdown.

### 10.3 Potential for a Fine-Tuned Model

At 10,000+ verified records, fine-tuning a small vision-language model (e.g., LLaVA-7B or similar) on the jewelry domain becomes feasible. This creates a fully offline, zero-API-cost prediction system deployable on a local machine — a significant cost and latency improvement for high-volume workshops.

---

## 11. Glossary

**CLIP** — Contrastive Language-Image Pretraining. A neural network that maps images to a shared embedding space with text, enabling visual similarity search without task-specific training.

**Cosine Similarity** — A measure of similarity between two vectors calculated as the cosine of the angle between them. Values range from -1 (opposite) to 1 (identical). Used to find similar ring images in the vector database.

**Embedding** — A dense numerical vector representation of an image or text, typically 128–1024 dimensions. Similar items have similar embeddings (small cosine distance).

**Ensemble** — Combining predictions from multiple models into a single final prediction, typically more accurate than any individual model.

**Ground Truth** — The actual, measured correct answer. In this system, ground truth is the post-casting gold weight measurement.

**Human-in-the-Loop** — A system design pattern where humans must verify or correct AI outputs before they are used as training data. Prevents model drift.

**Incremental / Continual Learning** — A training paradigm where a model is updated with new data without retraining from scratch on all historical data.

**Model Drift** — The gradual degradation of model accuracy over time, often caused by changes in input data distribution or training on incorrect labels.

**RAP (Retrieval-Augmented Prediction)** — A prediction architecture where retrieved similar examples are provided as context to an LLM or other model before it makes a prediction. Related to RAG (Retrieval-Augmented Generation) but applied to structured prediction tasks.

**Regression** — A type of machine learning task where the output is a continuous number (e.g., gold weight in grams), as opposed to classification where the output is a category.

**RMSE (Root Mean Squared Error)** — The standard deviation of prediction errors. An RMSE of 0.20g means the model's predictions are on average within ±0.20g of the actual gold weight.

**Vector Database** — A specialized database designed to store and efficiently search high-dimensional embedding vectors using approximate nearest-neighbor algorithms.

**XGBoost** — Extreme Gradient Boosting. A high-performance implementation of gradient-boosted decision trees, consistently the top performer on tabular regression and classification tasks at small-to-medium dataset sizes.

---

*This document is a living specification. Update it as the system evolves, new components are added, or design decisions change. Version it alongside the codebase.*
