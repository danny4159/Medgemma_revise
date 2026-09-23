import os

os.environ.setdefault(
    "HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache"
)
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import io

import torch
from PIL import Image
import requests
from transformers import pipeline

MODEL_ID = "google/medgemma-1.5-4b-it"


def main():
    pipe = pipeline(
        "image-text-to-text",
        model=MODEL_ID,
        torch_dtype=torch.bfloat16,
        device="cuda",
    )

    image_url = (
        "https://upload.wikimedia.org/wikipedia/commons/c/c8/"
        "Chest_Xray_PA_3-8-2010.png"
    )
    headers = {"User-Agent": "medgemma-smoke-test/1.0"}
    response = requests.get(image_url, headers=headers)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Describe this X-ray."},
            ],
        }
    ]

    output = pipe(text=messages, max_new_tokens=500)
    print(output[0]["generated_text"][-1]["content"])


if __name__ == "__main__":
    main()
