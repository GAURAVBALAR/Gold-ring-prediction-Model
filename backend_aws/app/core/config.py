from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from loguru import logger

class Settings(BaseSettings):
    PROJECT_NAME: str = "Gold Weight Prediction System"
    API_V1_STR: str = "/api/v1"
    
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    # Preferred LLM: "anthropic" or "gemini"
    DEFAULT_LLM: str = "gemini"
    
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/gold_weight.db"
    CHROMA_DB_PATH: str = "./data/chroma_db"
    
    # Vector DB Preference: "chroma" or "pinecone"
    VECTOR_DB_TYPE: str = "chroma"
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_INDEX_NAME: str = "ring-designs"
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
