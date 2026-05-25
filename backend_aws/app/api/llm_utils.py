import base64
import json
from google import genai
from anthropic import Anthropic
from app.core.config import settings
from loguru import logger
from PIL import Image
import io
import os

# Density Mapping (g/mm3)
GOLD_DENSITIES = {
    "14K": 0.01307,
    "18K": 0.01558,
    "22K": 0.01750,
    "24K": 0.01930
}

def calculate_weights_from_volume(volume_mm3: float):
    """Calculates karat-specific weights from volume in mm3."""
    return {
        "gold14k_g": volume_mm3 * GOLD_DENSITIES["14K"],
        "gold18k_g": volume_mm3 * GOLD_DENSITIES["18K"],
        "gold22k_g": volume_mm3 * GOLD_DENSITIES["22K"]
    }

def get_prompt(params: dict, similar_examples: list = None):
    examples_text = ""
    if similar_examples:
        examples_text = "\nRetrieved Visually Similar Examples (Historical Data):\n"
        for i, ex in enumerate(similar_examples):
            # ex['actual_volume_mm3'] is now pre-calculated in endpoints.py
            vol = ex.get('actual_volume_mm3', 0.0)
            examples_text += f"{i+1}. Name: {ex.get('product_name', 'N/A')}, Params: {json.dumps(ex['params'])}, Actual Weight: {ex['actual_weight']}g, Actual Volume: {vol:.2f}mm³\n"

    return f"""
    You are a jewelry manufacturing expert. Your goal is to estimate the VOLUME (mm³) of a ring design based on images.
    
    Input Parameters:
    {json.dumps(params, indent=2)}
    {examples_text}
    
    Calculation Baseline:
    - Standard gold 18k density: 15.58 g/cm³ (0.01558 g/mm³)
    - Use the 'Actual Volume' of similar examples as your primary anchor.
    
    Instructions:
    1. Analyze the images (multiple angles may be provided). Identify number of strands, thickness, and design complexity.
    2. Estimate the total material VOLUME in mm³.
    3. SAFETY MARGIN: Provide a volume RANGE (min to max). It is better to SLIGHTLY OVERESTIMATE volume for manufacturing safety.
    4. Return your response in JSON format.
    
    Expected JSON format:
    {{
        "min_volume_mm3": float,
        "max_volume_mm3": float,
        "explanation": "Detailed reasoning for volume estimation, specifically referencing the volume of similar examples",
        "design_notes": "Key observations from images"
    }}
    """

async def get_gemini_prediction(image_bytes_list: list[bytes], params: dict, api_key: str, similar_examples: list = None):
    logger.info(f"Initialising Gemini AI (gemini-3-flash-preview) with {len(image_bytes_list)} images...")
    
    try:
        # Using the new google-genai SDK
        client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
        model_id = 'gemini-2.5-flash'
        
        logger.info("Generating prompt...")
        prompt = get_prompt(params, similar_examples)
        
        logger.info(f"Requesting content from {model_id}...")
        
        # Prepare content with multiple images
        contents = [prompt]
        for img_bytes in image_bytes_list:
            img = Image.open(io.BytesIO(img_bytes))
            contents.append(img)
        
        response = client.models.generate_content(
            model=model_id,
            contents=contents
        )
        
        if not response or not response.text:
            raise ValueError("Empty response from Gemini API")

        logger.info("Response received from Gemini. Parsing...")
        text = response.text
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start == -1 or end == 0:
            logger.error(f"Failed to find JSON in response: {text}")
            raise ValueError("Gemini response did not contain valid JSON")

        result = json.loads(text[start:end])
        logger.info("JSON parsed successfully. Calculating weights...")
        
        min_vol = result.get("min_volume_mm3", 0.0)
        max_vol = result.get("max_volume_mm3", 0.0)
        
        # Calculate Karat weights in Backend for consistency
        min_weights_14k = min_vol * GOLD_DENSITIES["14K"]
        max_weights_14k = max_vol * GOLD_DENSITIES["14K"]
        min_weights_18k = min_vol * GOLD_DENSITIES["18K"]
        max_weights_18k = max_vol * GOLD_DENSITIES["18K"]
        min_weights_22k = min_vol * GOLD_DENSITIES["22K"]
        max_weights_22k = max_vol * GOLD_DENSITIES["22K"]
        
        return {
            "estimated_volume_mm3": max_vol,
            "min_weight_14k": min_weights_14k,
            "max_weight_14k": max_weights_14k,
            "min_weight_18k": min_weights_18k,
            "max_weight_18k": max_weights_18k,
            "min_weight_22k": min_weights_22k,
            "max_weight_22k": max_weights_22k,
            "predicted_weight_14k": max_weights_14k,
            "predicted_weight_18k": max_weights_18k,
            "explanation": result.get("explanation", "No explanation provided."),
            "raw": result
        }
    except Exception as e:
        logger.error(f"Gemini API error detail: {str(e)}")
        raise e

async def get_anthropic_prediction(image_bytes: bytes, params: dict, api_key: str, similar_examples: list = None):
    logger.info("Initialising Anthropic AI...")
    if not api_key or api_key == "your_anthropic_key":
        logger.warning("Invalid Anthropic API Key detected!")
        raise ValueError("Invalid Anthropic API Key")

    client = Anthropic(api_key=api_key)
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = get_prompt(params, similar_examples)

    try:
        logger.info("Requesting content from Claude API...")
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
        )
        text = message.content[0].text
        start = text.find('{')
        end = text.rfind('}') + 1
        result = json.loads(text[start:end])
        return {
            "predicted_weight_14k": result.get("gold14k_g"),
            "predicted_weight_18k": result.get("gold18k_g"),
            "explanation": result.get("explanation"),
            "raw": result
        }
    except Exception as e:
        logger.error(f"Anthropic API error: {e}")
        raise e

async def get_llm_prediction(image_bytes_list: list[bytes], params: dict, config: dict, similar_examples: list = None):
    provider = config.get("default_llm", settings.DEFAULT_LLM)
    gemini_key = config.get("gemini_api_key") or settings.GEMINI_API_KEY
    anthropic_key = config.get("anthropic_api_key") or settings.ANTHROPIC_API_KEY
    
    try:
        if provider == "gemini" and gemini_key:
            return await get_gemini_prediction(image_bytes_list, params, gemini_key, similar_examples)
        elif provider == "anthropic" and anthropic_key:
            # Anthropic only uses the first image for now
            return await get_anthropic_prediction(image_bytes_list[0], params, anthropic_key, similar_examples)
        else:
            # Fallback
            if gemini_key:
                return await get_gemini_prediction(image_bytes_list, params, gemini_key, similar_examples)
            
            return {
                "predicted_weight_14k": 0.0,
                "predicted_weight_18k": 0.0,
                "explanation": "No API keys set",
                "raw": {}
            }
    except Exception as e:
        logger.error(f"All LLM providers failed: {e}")
        return {
            "predicted_weight_14k": 0.0,
            "predicted_weight_18k": 0.0,
            "explanation": f"Error: {str(e)}",
            "raw": {}
        }
