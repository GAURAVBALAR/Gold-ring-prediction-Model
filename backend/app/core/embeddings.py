import os
import io
from PIL import Image
from loguru import logger
from typing import List, Optional
from app.core.config import settings

# Lazy-loaded CLIP variables
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_clip_device = None

def _init_clip():
    """Lazy initialization of CLIP model to prevent import errors on cloud."""
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device
    if _clip_model is not None:
        return
        
    logger.info("Initializing local CLIP ViT-B-32 model...")
    try:
        import torch
        import open_clip
    except ImportError as e:
        logger.error("Failed to import torch or open_clip. Make sure they are installed for local embeddings.")
        raise e
        
    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading CLIP model on {_clip_device}...")
    _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k", device=_clip_device
    )
    _clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
    logger.info("CLIP model loaded successfully.")


# Gemini embedding logic
async def _get_gemini_image_embedding(image_bytes: bytes, api_key: str) -> List[float]:
    from google import genai
    # Initialize genai Client
    client = genai.Client(api_key=api_key)
    image = Image.open(io.BytesIO(image_bytes))
    prompt = "Describe this piece of jewelry in extreme technical detail for visual similarity search. Focus on: type, material color, stone settings, patterns, and structure."
    
    # 1. Run Gemini vision model to describe the jewelry
    # Run in executor to prevent blocking the event loop
    import asyncio
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image]
        )
    )
    description = response.text
    logger.info(f"Gemini jewelry description generated: {description[:80]}...")
    
    # 2. Get text embedding of the generated description
    result = await loop.run_in_executor(
        None,
        lambda: client.models.embed_content(
            model='gemini-embedding-2',
            contents=description
        )
    )
    return result.embeddings[0].values

async def _get_gemini_text_embedding(text: str, api_key: str) -> List[float]:
    from google import genai
    client = genai.Client(api_key=api_key)
    import asyncio
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.models.embed_content(
            model='gemini-embedding-2',
            contents=text
        )
    )
    return result.embeddings[0].values


# Standardized public API
async def get_image_embedding(image_bytes: bytes, gemini_api_key: Optional[str] = None) -> List[float]:
    """Exposes unified interface to get image embedding based on settings.EMBEDDING_TYPE."""
    emb_type = settings.EMBEDDING_TYPE.lower()
    
    if emb_type == "gemini":
        key = gemini_api_key or settings.GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY must be set in settings or passed to run Gemini embeddings")
        return await _get_gemini_image_embedding(image_bytes, key)
    else:
        # Default to CLIP
        _init_clip()
        import torch
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_input = _clip_preprocess(image).unsqueeze(0).to(_clip_device)
        
        # Run cpu/gpu operations in executor to avoid blocking main thread if heavy
        import asyncio
        loop = asyncio.get_running_loop()
        
        def run_clip_inference():
            with torch.no_grad():
                image_features = _clip_model.encode_image(image_input)
                image_features /= image_features.norm(dim=-1, keepdim=True)
            return image_features.cpu().numpy().tolist()[0]
            
        return await loop.run_in_executor(None, run_clip_inference)

async def get_text_embedding(text: str, gemini_api_key: Optional[str] = None) -> List[float]:
    """Exposes unified interface to get text embedding based on settings.EMBEDDING_TYPE."""
    emb_type = settings.EMBEDDING_TYPE.lower()
    
    if emb_type == "gemini":
        key = gemini_api_key or settings.GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY must be set in settings or passed to run Gemini embeddings")
        return await _get_gemini_text_embedding(text, key)
    else:
        # CLIP text embedding
        _init_clip()
        import torch
        text_input = _clip_tokenizer(text).to(_clip_device)
        
        import asyncio
        loop = asyncio.get_running_loop()
        
        def run_clip_text_inference():
            with torch.no_grad():
                text_features = _clip_model.encode_text(text_input)
                text_features /= text_features.norm(dim=-1, keepdim=True)
            return text_features.cpu().numpy().tolist()[0]
            
        return await loop.run_in_executor(None, run_clip_text_inference)

def get_embedding_dimension() -> int:
    """Returns the dimension size of the current embedding model."""
    emb_type = settings.EMBEDDING_TYPE.lower()
    if emb_type == "gemini":
        return 3072
    return 512
