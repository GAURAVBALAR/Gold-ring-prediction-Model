import requests

url = "http://localhost:8000/api/v1/predict"
image_path = "../WhatsApp Image 2026-04-29 at 2.41.17 PM (1).jpeg"

    "images": open("../../WhatsApp Image 2026-04-29 at 2.41.17 PM (1).jpeg", "rb")
data = {
    "ring_size": 6.5,
    "karat": "14K",
    "style": "bypass",
    "product_name": "Two stone bypass ring"
}

try:
    response = requests.post(url, files=files, data=data)
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)
except Exception as e:
    print("ERROR:", e)
