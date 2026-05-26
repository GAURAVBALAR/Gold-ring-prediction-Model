from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router
from app.api.settings import router as settings_router
from app.core.config import settings
from app.db.session import Base
from sqlalchemy import create_engine as create_sync_engine
from loguru import logger
import os

app = FastAPI(title=settings.PROJECT_NAME)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(settings_router, prefix=settings.API_V1_STR, tags=["settings"])

@app.on_event("startup")
async def startup():
    # Ensure data and images directories exist FIRST
    data_dir = "data"
    images_dir = os.path.join(data_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    logger.info(f"Data directories ready: {os.path.abspath(data_dir)}")

    # Use a SYNCHRONOUS engine for schema creation to avoid the aiosqlite
    # greenlet context error that occurs during CREATE INDEX statements.
    # Runtime DB queries still use the async engine via get_db().
    try:
        sync_db_url = settings.DATABASE_URL.replace(
            "sqlite+aiosqlite://", "sqlite://"
        )
        sync_engine = create_sync_engine(
            sync_db_url,
            echo=True,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(sync_engine)
        sync_engine.dispose()
        logger.info("Database tables created / verified successfully.")
    except Exception as exc:
        logger.error(f"Database initialisation failed: {exc}")
        raise

    # Mount /data/images AFTER the directory is guaranteed to exist
    try:
        app.mount("/data/images", StaticFiles(directory=images_dir), name="images")
    except Exception:
        pass  # Already mounted (hot-reload)

# Serve frontend static files
if os.path.isdir("static"):
    try:
        app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
    except Exception:
        pass  # Already mounted

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        if full_path.startswith("api/") or full_path.startswith("data/"):
            return {"detail": "Not Found"}

        static_file_path = os.path.join("static", full_path)
        if os.path.isfile(static_file_path):
            return FileResponse(static_file_path)

        # Fallback to index.html for SPA
        return FileResponse(os.path.join("static", "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "Welcome to the Gold Weight Prediction API"}

