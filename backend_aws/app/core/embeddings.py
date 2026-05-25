from typing import List
from google import genai
from PIL import Image
import io
from app.core.config import settings
from loguru import logger

class EmbeddingManager:
    """
    Lite Embedding Manager for Cloud (No Torch/CLIP).
    Uses Gemini Vision to describe the image, then embeds the description.
    """
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.vision_model = 'gemini-2.5-flash'
        self.text_model = "gemini-embedding-2"

    async def get_image_embedding(self, image_data: bytes) -> List[float]:
        image = Image.open(io.BytesIO(image_data))
        prompt = "Describe this piece of jewelry in extreme technical detail for visual similarity search. Focus on: type, material color, stone settings, patterns, and structure."
        
        response = self.client.models.generate_content(
            model=self.vision_model,
            contents=[prompt, image]
        )
        description = response.text
        
        result = self.client.models.embed_content(
            model=self.text_model,
            contents=description
        )
        return result.embeddings[0].values

    async def get_text_embedding(self, text: str) -> List[float]:
        result = self.client.models.embed_content(
            model=self.text_model,
            contents=text
        )
        return result.embeddings[0].values

embedding_manager = EmbeddingManager()
