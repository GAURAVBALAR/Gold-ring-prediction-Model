from fastapi import FastAPI
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

@app.get("/")
async def root():
    return {"message": "Welcome to the Gold Weight Prediction API"}
