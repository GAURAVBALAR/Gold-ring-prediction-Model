from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router as api_router
from app.api.settings import router as settings_router
from app.core.config import settings
from app.db.session import engine, Base
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

# Serve static images
os.makedirs("data/images", exist_ok=True)
app.mount("/data/images", StaticFiles(directory="data/images"), name="images")

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(settings_router, prefix=settings.API_V1_STR, tags=["settings"])

@app.on_event("startup")
async def startup():
    # Ensure data and images directories exist
    data_dir = "data"
    images_dir = os.path.join(data_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Serve frontend static files
if os.path.isdir("static"):
    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        if full_path.startswith("api/") or full_path.startswith("data/"):
            # Let API routes pass through if they 404
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
