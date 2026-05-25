import os
import time
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

# Load environment variables
load_dotenv("./backend/.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
NEW_INDEX_NAME = "ring-designs-v2"

if not PINECONE_API_KEY:
    print("Error: PINECONE_API_KEY not found in backend/.env")
    exit(1)

def setup_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    
    if NEW_INDEX_NAME in existing_indexes:
        print(f"Index '{NEW_INDEX_NAME}' already exists.")
    else:
        print(f"Creating new index: {NEW_INDEX_NAME}...")
        pc.create_index(
            name=NEW_INDEX_NAME,
            dimension=512, # CLIP dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        
        print("Waiting for index to be ready...")
        while not pc.describe_index(NEW_INDEX_NAME).status['ready']:
            time.sleep(2)
        print(f"Index '{NEW_INDEX_NAME}' is ready!")

if __name__ == "__main__":
    setup_index()
