from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import os

# Ensure the SQLite data directory exists BEFORE the engine is created.
# aiosqlite cannot create parent directories automatically.
_db_url = settings.DATABASE_URL
if "sqlite" in _db_url:
    # Extract path from sqlite+aiosqlite:///./data/gold_weight.db
    _db_path = _db_url.split("///")[-1].lstrip("./")
    _db_dir = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
