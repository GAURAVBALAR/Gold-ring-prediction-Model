from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class PredictionCreate(BaseModel):
    ring_size: Optional[float] = None
    inner_diameter_mm: Optional[float] = None
    band_width_mm: Optional[float] = None
    band_thickness_mm: Optional[float] = None
    stone_length_mm: Optional[float] = None
    stone_width_mm: Optional[float] = None
    stone_ct: Optional[float] = None
    side_stone_count: Optional[int] = 0
    side_stone_ct: Optional[float] = 0.0

class PredictionResponse(BaseModel):
    id: int
    predicted_weight_14k: float
    predicted_weight_18k: float
    
    # Volume base
    estimated_volume_mm3: Optional[float] = None
    
    # Range fields
    min_weight_14k: Optional[float] = None
    max_weight_14k: Optional[float] = None
    min_weight_18k: Optional[float] = None
    max_weight_18k: Optional[float] = None
    min_weight_22k: Optional[float] = None
    max_weight_22k: Optional[float] = None
    
    llm_explanation: Optional[str] = None
    actual_weight_g: Optional[float] = None
    actual_karat: Optional[str] = None
    created_at: datetime
    image_path: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class SimilarExample(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    params: Dict[str, Any]
    actual_weight: float
    actual_volume_mm3: Optional[float] = None
    score: float

class PredictionFeedback(BaseModel):
    prediction_id: int
    is_correct: bool
    actual_weight_g: Optional[float] = None
    actual_karat: Optional[str] = None # e.g. "18K"
    actual_diamond_carat: Optional[float] = 0.0

class UnifiedPredictionResponse(BaseModel):
    prediction: PredictionResponse
    similar_examples: List[SimilarExample]
    xgboost_prediction_14k: Optional[float] = None
    ensemble_applied: Optional[bool] = None

# Verified Design (Training Data)
class VerifiedDesignCreate(BaseModel):
    product_name: str
    karat: str
    actual_weight_g: float
    ring_size: Optional[float] = None
    stone_ct: Optional[float] = 0.0

class VerifiedDesignResponse(BaseModel):
    id: int
    product_name: str
    karat: str
    actual_weight_g: float
    estimated_volume_mm3: Optional[float] = None
    image_path: str
    created_at: datetime

    class Config:
        from_attributes = True
