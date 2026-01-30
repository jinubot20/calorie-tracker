import google.generativeai as genai
import PIL.Image
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Configure the Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def estimate_calories(image_paths: list = None, user_description: str = None):
    """
    Analyzes multiple images and/or description to estimate calories and macros.
    """
    # Using gemini-2.5-flash as requested
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    contents = []
    
    if image_paths:
        for path in image_paths:
            # Standardize image to RGB JPEG
            temp_processed_path = f"{path}_processed.jpg"
            try:
                with PIL.Image.open(path) as img:
                    rgb_img = img.convert('RGB')
                    rgb_img.save(temp_processed_path, 'JPEG')
                contents.append(PIL.Image.open(temp_processed_path))
            except Exception as e:
                print(f"Error processing {path}: {e}")

    desc_part = f"\nUser description: {user_description}" if user_description else ""
    
    prompt = f"""
    Identify the food described/shown and estimate the TOTAL calories and macros (protein, carbs, fat in grams).
    If multiple images are provided, they represent different parts of the SAME meal. Calculate the total for everything shown.
    {desc_part}
    
    CRITICAL INSTRUCTION FOR ACCURACY:
    Look for common reference objects in the photo (like a fork, spoon, or human hand/palm) to judge the scale and volume of the food. 
    Use these objects as a "ruler" to provide more accurate estimates. If no reference object is visible, use standard plate/bowl sizes as context.
    
    Provide the response strictly as a JSON object:
    {{
      "food": "Food Name",
      "calories": 0,
      "protein": 0,
      "carbs": 0,
      "fat": 0
    }}
    """
    contents.insert(0, prompt)
    
    try:
        response = model.generate_content(contents)
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        data = json.loads(clean_text)
        return (
            data.get("food", "Unknown"), 
            data.get("calories", 0),
            data.get("protein", 0),
            data.get("carbs", 0),
            data.get("fat", 0)
        )
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower() or "limit" in error_msg.lower():
            # Signal the caller that we hit the AI quota limit
            raise Exception("AI_QUOTA_REACHED")
        print(f"Error estimating calories: {e}")
        return "Unknown", 0, 0, 0, 0

def generate_daily_summary(meals_list, target_calories):
    """
    Generates a human-friendly summary acting as a nutrition coach.
    """
    if not meals_list:
        return "No data recorded for today."

    model = genai.GenerativeModel('gemini-2.5-flash')
    
    meals_data = [
        {"food": m.food_name, "desc": m.description, "cal": m.calories, "p": m.protein, "c": m.carbs, "f": m.fat}
        for m in meals_list
    ]
    
    total_consumed = sum(m['cal'] for m in meals_data)
    
    prompt = f"""
    You are an expert AI Nutrition Coach for the app "Fuel".
    
    Your goal is to analyze the user's meals and give actionable, encouraging advice based on their target.
    User's Daily Calorie Target: {target_calories} kcal
    Total Calories Consumed Today: {total_consumed} kcal
    
    Meals Logged Today: {json.dumps(meals_data)}
    
    Instructions:
    1. Compare consumed vs target. 
    2. Analyze macros (prioritize protein).
    3. Suggest ONE specific "cut" or "swap" to improve nutrition quality or hit the target better.
    4. Keep the note brief (3-4 sentences), encouraging, and professional.
    
    Example: "You're currently 200kcal under your target—great room for a protein snack! I noticed lunch was quite high in fats from the dressing; swapping to a balsamic vinaigrette tomorrow could save you about 150kcal while keeping the flavor."
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return "You're doing great! Keep tracking your meals to see patterns."
