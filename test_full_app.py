import os
import psutil
import time
import subprocess
import requests

env = os.environ.copy()
env["PYTHONPATH"] = "backend:" + env.get("PYTHONPATH", "")
process = subprocess.Popen(["../venv/bin/python", "-m", "uvicorn", "app.main:app", "--port", "8001"], cwd="backend", env=env)
time.sleep(5) # wait for startup

# Create a fake image and send a predict request
with open("test.png", "wb") as f:
    f.write(b"fake image data")

print("Sending first request to load CLIP into memory...")
try:
    requests.post("http://127.0.0.1:8001/api/v1/predict", files={"images": open("test.png", "rb")}, data={"ring_size": 10})
except Exception as e:
    pass

time.sleep(5)
try:
    mem_info = psutil.Process(process.pid).memory_info()
    print(f"Backend Server RAM Usage AFTER Loading AI: {mem_info.rss / (1024 * 1024):.2f} MB")
except Exception as e:
    print("Error getting mem info:", e)

process.terminate()
