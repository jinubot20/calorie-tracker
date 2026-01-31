import requests
import json
import sqlite3
import os
import google.generativeai as genai
from rapidfuzz import process, fuzz
from dotenv import load_dotenv

load_dotenv()

# Configuration
DB_PATH = "calorie_tracker.db"
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
HPB_DETAILS_URL = "https://pphtpc.hpb.gov.sg/bff/v1/food-portal/foods/details/{crId}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def get_hpb_candidates():
    """Retrieve all food names and crIds from local DB."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, crId, description FROM hpb_foods")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r[0], "crId": r[1], "desc": r[2]} for r in rows]

def fetch_hpb_details(crId):
    """Fetch nutrition data for a specific crId."""
    try:
        url = HPB_DETAILS_URL.format(crId=crId)
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            nutrients = data.get("calculatedFoodNutrients", {})
            return {
                "calories": round(nutrients.get("energy", 0)),
                "protein": round(nutrients.get("protein", 0)),
                "carbs": round(nutrients.get("carbohydrate", 0)),
                "fat": round(nutrients.get("fat", 0))
            }
    except Exception as e:
        print(f"Error fetching HPB details for {crId}: {e}")
    return None

def estimate_calories(image_paths: list = None, user_description: str = None):
    # Pass 1: Identification & Segmentation
    model = genai.GenerativeModel('gemini-flash-lite-latest')
    
    contents = []
    if image_paths:
        import PIL.Image
        for path in image_paths:
            contents.append(PIL.Image.open(path))

    desc_part = f"\nUser description: {user_description}" if user_description else ""
    
    id_prompt = f"""
    Identify every distinct food item and drink in this meal. 
    Focus only on the primary subject. 
    {desc_part}
    Respond with a simple comma-separated list of items.
    Example: Hainanese Chicken Rice, Iced Coffee, Fried Egg
    """
    
    try:
        response = model.generate_content([id_prompt] + contents)
        identified_items = [x.strip() for x in response.text.split(',')]
        
        # Pass 2: Candidate Retrieval (Local Fuzzy Search)
        hpb_list = get_hpb_candidates()
        all_matches = []
        
        for item in identified_items:
            # Get top 10 similar items from HPB list
            matches = process.extract(item, [h['name'] for h in hpb_list], scorer=fuzz.WRatio, limit=10)
            candidates = []
            for match_name, score, idx in matches:
                candidates.append(hpb_list[idx])
            all_matches.append({"query": item, "candidates": candidates})

        # Pass 3: Grounded Judging & Portions
        judge_prompt = f"""
        You are a nutrition expert matching real meals to an official database.
        
        Original User Description: {user_description}
        Identified Items: {", ".join(identified_items)}
        
        For each item identified, look at the photo and pick the best match from the provided HPB candidates.
        Also, estimate the portion (1.0 = standard, 0.5 = half, 1.5 = large). 
        Prioritize user text for portions (e.g., if user says "half", use 0.5).
        
        HPB CANDIDATES:
        {json.dumps(all_matches)}
        
        If an item has NO reasonable match in the list, set "crId" to null and provide your own best estimate for macros.
        
        Return JSON:
        {{
          "food_summary": "Overall Meal Name",
          "items": [
            {{"name": "Item Name", "crId": "FXXXX", "portion": 1.0, "est_cal": 0, "est_p": 0, "est_c": 0, "est_f": 0}}
          ]
        }}
        """
        
        judge_resp = model.generate_content([judge_prompt] + contents)
        clean_json = judge_resp.text.strip().replace('```json', '').replace('```', '')
        result_data = json.loads(clean_json)
        
        # Final Calculation
        total_cal = 0
        total_p = 0
        total_c = 0
        total_f = 0
        final_items = []
        
        for item in result_data.get("items", []):
            portion = item.get("portion", 1.0)
            if item.get("crId"):
                # Use HPB Data
                hpb_data = fetch_hpb_details(item["crId"])
                if hpb_data:
                    total_cal += round(hpb_data["calories"] * portion)
                    total_p += round(hpb_data["protein"] * portion)
                    total_c += round(hpb_data["carbs"] * portion)
                    total_f += round(hpb_data["fat"] * portion)
                    final_items.append({"name": item["name"], "portion": portion})
                    continue
            
            # Fallback to LLM estimate
            total_cal += round(item.get("est_cal", 0) * portion)
            total_p += round(item.get("est_p", 0) * portion)
            total_c += round(item.get("est_c", 0) * portion)
            total_f += round(item.get("est_f", 0) * portion)
            final_items.append({"name": item["name"], "portion": portion})

        return (
            result_data.get("food_summary", "Unknown"),
            total_cal, total_p, total_c, total_f,
            final_items
        )

    except Exception as e:
        print(f"Pipeline Error: {e}")
        return "Unknown", 0, 0, 0, 0, []
