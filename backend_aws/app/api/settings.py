from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.settings import SystemSetting
from pydantic import BaseModel
from typing import Dict
from app.core.config import settings as app_settings

router = APIRouter()

class SettingsUpdate(BaseModel):
    default_llm: str
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

@router.get("/settings")
async def get_system_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSetting))
    db_settings = {s.key: s.value for s in result.scalars().all()}
    
    # Return merged with env defaults
    return {
        "default_llm": db_settings.get("default_llm", app_settings.DEFAULT_LLM),
        "anthropic_api_key": db_settings.get("anthropic_api_key", app_settings.ANTHROPIC_API_KEY or ""),
        "gemini_api_key": db_settings.get("gemini_api_key", app_settings.GEMINI_API_KEY or ""),
        "has_anthropic": bool(db_settings.get("anthropic_api_key") or app_settings.ANTHROPIC_API_KEY),
        "has_gemini": bool(db_settings.get("gemini_api_key") or app_settings.GEMINI_API_KEY)
    }

@router.post("/settings")
async def update_system_settings(update: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    settings_dict = update.dict()
    
    for key, value in settings_dict.items():
        # Get existing or create new
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await db.execute(stmt)
        db_setting = result.scalar_one_or_none()
        
        if db_setting:
            db_setting.value = value
        else:
            db_setting = SystemSetting(key=key, value=value)
            db.add(db_setting)
            
    await db.commit()
    return {"message": "Settings updated successfully"}
