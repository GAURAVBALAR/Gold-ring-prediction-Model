from sqlalchemy import Column, Integer, Float, String, DateTime, JSON
from datetime import datetime
from app.db.session import Base

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    ring_size = Column(Float, nullable=True)
    inner_diameter_mm = Column(Float, nullable=True)
    band_width_mm = Column(Float, nullable=True)
    band_thickness_mm = Column(Float, nullable=True)
    stone_length_mm = Column(Float, nullable=True)
    stone_width_mm = Column(Float, nullable=True)
    stone_ct = Column(Float, nullable=True)
    side_stone_count = Column(Integer, nullable=True)
    side_stone_ct = Column(Float, nullable=True)
    
    image_path = Column(String)
    
    # Core Base Metric
    estimated_volume_mm3 = Column(Float, nullable=True)
    
    predicted_weight_14k = Column(Float)
    predicted_weight_18k = Column(Float)
    
    # Range fields
    min_weight_14k = Column(Float, nullable=True)
    max_weight_14k = Column(Float, nullable=True)
    min_weight_18k = Column(Float, nullable=True)
    max_weight_18k = Column(Float, nullable=True)
    min_weight_22k = Column(Float, nullable=True)
    max_weight_22k = Column(Float, nullable=True)
    
    llm_explanation = Column(String)
    raw_response = Column(JSON)
    
    actual_weight_g = Column(Float, nullable=True)
    actual_karat = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class VerifiedDesign(Base):
    __tablename__ = "verified_designs"

    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String)
    karat = Column(String) # e.g. "18K"
    actual_weight_g = Column(Float)
    estimated_volume_mm3 = Column(Float, nullable=True)
    
    # Geometric metadata
    ring_size = Column(Float, nullable=True)
    stone_ct = Column(Float, nullable=True)
    
    image_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
