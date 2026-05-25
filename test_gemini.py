from google import genai
import os
from dotenv import load_dotenv

load_dotenv("backend/.env", override=True)
api_key = os.getenv("GEMINI_API_KEY")

print(f"Loaded API Key: {api_key[:5]}...{api_key[-5:] if api_key else ''}")

if not api_key or "your_gemini_key" in api_key:
    print("Error: GEMINI_API_KEY is still a placeholder.")
else:
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    model_name = 'gemini-3-flash-preview'
    print(f"\nTesting with {model_name} using new google-genai SDK...")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Hello! Are you working? Reply with YES."
        )
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error with {model_name}: {e}")
