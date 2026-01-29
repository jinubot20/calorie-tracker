import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def generate(prompt):
    # Testing the Imagen model via Gemini API
    # Note: AI Studio recently added Imagen 3
    try:
        model = genai.GenerativeModel('gemini-3-pro-image-preview')
        print(f"Generating image for: {prompt}")
        response = model.generate_content(prompt)
        
        # In the python SDK, image response handling depends on the version
        # Usually it returns an image object in the response
        if response.candidates:
            # Save the first image
            img = response.candidates[0].content.parts[0].inline_data.data
            with open("generated_test.png", "wb") as f:
                f.write(img)
            print("Successfully saved to generated_test.png")
        else:
            print("No image generated in response.")
            print(response)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate("A beautiful futuristic city in Singapore with lush greenery and flying cars, cinematic lighting, 8k")
