from zhipuai import ZhipuAI
import os
import requests
from dotenv import load_dotenv

load_dotenv()
client = ZhipuAI(api_key=os.getenv("ZHIPUAI_API_KEY"))

def generate(prompt):
    try:
        print(f"Generating image with CogView-3 for: {prompt}")
        response = client.images.generations(
            model="cogview-3-flash", # Testing flash model
            prompt=prompt,
        )
        url = response.data[0].url
        print(f"Success! Image URL: {url}")
        
        # Download the image
        img_data = requests.get(url).content
        with open("generated_zai_test.png", "wb") as f:
            f.write(img_data)
        print("Saved to generated_zai_test.png")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate("A beautiful futuristic city in Singapore with lush greenery and flying cars, cinematic lighting, 8k")
