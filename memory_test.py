import os
import psutil
import torch
import open_clip

def print_memory(step):
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    print(f"{step} - RAM Usage: {mem_info.rss / (1024 * 1024):.2f} MB")

print_memory("1. Initial Baseline")

print("Loading PyTorch and Open_CLIP...")
model_name = "ViT-B-32"
pretrained = "laion2b_s34b_b79k"

model, _, preprocess = open_clip.create_model_and_transforms(
    model_name, pretrained=pretrained, device="cpu"
)
print_memory("2. After Loading CLIP Model")

# Simulate a quick prediction
from PIL import Image
import io
img = Image.new('RGB', (224, 224), color = 'red')
image_input = preprocess(img).unsqueeze(0)
with torch.no_grad():
    image_features = model.encode_image(image_input)
    
print_memory("3. After First Inference")
