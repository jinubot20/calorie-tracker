import requests
import json
import sqlite3
import os
import math
import logging
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configuration
DB_PATH = "calorie_tracker.db"

# API Key Rotation Logic
PRIMARY_KEY = os.getenv("GOOGLE_API_KEY")
SECONDARY_KEY = os.getenv("GOOGLE_API_KEY_2")

def get_rotating_key():
    """Simple toggle between two keys based on a counter file or random."""
    if not SECONDARY_KEY:
        return PRIMARY_KEY
    
    # We'll use a local file to persist the toggle state across restarts/worker processes
    toggle_file = "api_toggle.tmp"
    try:
        if os.path.exists(toggle_file):
            with open(toggle_file, "r") as f:
                state = f.read().strip()
            new_state = "secondary" if state == "primary" else "primary"
        else:
            new_state = "secondary"
            
        with open(toggle_file, "w") as f:
            f.write(new_state)
            
        return SECONDARY_KEY if new_state == "secondary" else PRIMARY_KEY
    except:
        return PRIMARY_KEY

def configure_genai(key_index=None):
    """Configure genai with a specific key or the current rotating key."""
    if key_index == 0:
        genai.configure(api_key=PRIMARY_KEY)
        return PRIMARY_KEY
    if key_index == 1:
        genai.configure(api_key=SECONDARY_KEY)
        return SECONDARY_KEY
        
    key = get_rotating_key()
    genai.configure(api_key=key)
    return key

HPB_DETAILS_URL = "https://pphtpc.hpb.gov.sg/bff/v1/food-portal/foods/details/{crId}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def cosine_similarity(v1, v2):
    dot_product = sum(x*y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x*x for x in v1))
    magnitude2 = math.sqrt(sum(x*x for x in v2))
    return dot_product / (magnitude1 * magnitude2) if magnitude1 and magnitude2 else 0

def get_semantic_candidates(query, limit=10):
    """Retrieve top candidates from local DB using vector similarity."""
    try:
        configure_genai()
        # 1. Embed the query
        res = genai.embed_content(
            model="models/text-embedding-004", 
            content=query, 
            task_type="retrieval_query"
        )
        query_vec = res['embedding']
        
        # 2. Get all embeddings from DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.name, h.crId, h.description, e.embedding 
            FROM hpb_foods h 
            JOIN hpb_embeddings e ON h.crId = e.crId
        """)
        rows = cursor.fetchall()
        conn.close()
        
        # 3. Rank by similarity
        scored_items = []
        for name, crId, desc, emb_json in rows:
            emb = json.loads(emb_json)
            score = cosine_similarity(query_vec, emb)
            scored_items.append({"name": name, "crId": crId, "desc": desc, "score": score})
            
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        return scored_items[:limit]
    except Exception as e:
        print(f"Semantic search error: {e}")
        return []

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
    # Model Rotation Pool: We'll try the best ones first
    # 2.0-flash-lite is great for text/simple, but 1.5-flash is robust for vision
    MODELS_TO_TRY = [
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash-latest',
        'gemini-2.0-flash'
    ]
    
    # Try both keys
    keys_to_try = [0, 1] if SECONDARY_KEY else [0]
    current_key_idx = 0 if get_rotating_key() == PRIMARY_KEY else 1
    if current_key_idx == 1:
        keys_to_try = [1, 0]
    
    last_error = None
    
    # Nested loop: For each key, try rotating models if we hit a 429
    for k_idx in keys_to_try:
        configure_genai(k_idx)
        
        for m_name in MODELS_TO_TRY:
            try:
                print(f"Attempting analysis with Key {k_idx} and Model {m_name}...")
                model = genai.GenerativeModel(m_name)
                
                contents = []
                processed_temp_files = []
                
                if image_paths:
                    import PIL.Image
                    for path in image_paths:
                        temp_path = f"{path}_std.jpg"
                        try:
                            with PIL.Image.open(path) as img:
                                if getattr(img, "n_frames", 1) > 1:
                                    img.seek(0)
                                rgb_img = img.convert('RGB')
                                rgb_img.save(temp_path, 'JPEG')
                            contents.append(PIL.Image.open(temp_path))
                            processed_temp_files.append(temp_path)
                        except Exception as e:
                            print(f"Error standardizing image {path}: {e}")
                            try:
                                contents.append(PIL.Image.open(path))
                            except:
                                pass

                desc_part = f"\nUser description: {user_description}" if user_description else ""
                
                id_prompt = f"""
                Identify every distinct food item and drink in this meal. 
                
                STRICT SUBJECT RULES:
                1. PRIMARY ONLY: Focus ONLY on the items that are the main subject of the photo (usually centered and in focus). 
                2. IGNORE EDGES: Completely ignore any food, drink, or containers at the extreme edges, borders, or corners of the frame. 
                3. IGNORE CROPPED: If an item is partially cut off by the edge of the photo, OMIT it entirely.
                4. IGNORE BACKGROUND: Ignore items belonging to other people or sitting in the background.
                
                {desc_part}
                Respond with a simple comma-separated list of items.
                Example: Hainanese Chicken Rice, Iced Coffee, Fried Egg
                """
                
                response = model.generate_content([id_prompt] + contents)
                text = response.text.strip()
                if '\n' in text:
                    for line in text.split('\n'):
                        if ',' in line:
                            identified_items = [x.strip() for x in line.split(',')]
                            break
                    else:
                        identified_items = [x.strip() for x in text.split('\n')][-1].split(',')
                else:
                    identified_items = [x.strip() for x in text.split(',')]
                
                # Pass 2: Candidate Retrieval (Semantic Search)
                all_matches = []
                for item in identified_items:
                    candidates = get_semantic_candidates(item, limit=10)
                    all_matches.append({"query": item, "candidates": candidates})

                # Pass 3: Grounded Judging & Portions
                judge_prompt = f"""
                You are a nutrition expert matching real meals to an official database.
                
                Original User Description: {user_description}
                Identified Items: {", ".join(identified_items)}
                
                For each item identified, look at the photo (if provided) and pick the best match from the provided HPB candidates.
                
                CRITICAL INSTRUCTION FOR ACCURACY:
                1. USER TEXT PRIORITY: If the user mentions a quantity or portion (e.g., "5 pieces", "half", "1 slice", "shared"), you MUST use that instead of the visual.
                2. THE "BISCUIT" RULE: For Cream Crackers or Biscuits, the HPB database standard is 1 PIECE. If a user says "5 pieces", you MUST set portion to 5.0.
                3. NO IMAGE RULE: If NO images are provided, assume standard serving (portion: 1.0) for identified items UNLESS a quantity is specified in the text.
                4. THE "SLICE" RULE: Items like "Ngoh Hiang" or "Fish Cake" are often defined as a WHOLE ROLL. If the user mentions a "SLICE", adjust portion to ~0.1 - 0.2.
                5. THE "DAB" RULE: For condiments like Sambal, Chili, or Soy Sauce, if it is a small side portion (e.g. in a plastic saucer or on the side), adjust portion to ~0.1 (approx 10-15 kcal). Do not treat it as a main dish.
                6. STRICT PRIMARY FOCUS: Strictly OMIT any items that are at the edges, corners, or partially cropped out of the frame. Focus only on the central, intended subject of the meal.
                7. PORTION SCALING: 1.0 = standard serving, 0.5 = half, 1.5 = large. Lean toward 1.0 for health-conscious users unless cues are obvious.
                
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
                resp_text = judge_resp.text.strip()
                
                if '```json' in resp_text:
                    clean_json = resp_text.split('```json')[1].split('```')[0].strip()
                elif '```' in resp_text:
                    clean_json = resp_text.split('```')[1].split('```')[0].strip()
                else:
                    start = resp_text.find('{')
                    end = resp_text.rfind('}')
                    clean_json = resp_text[start:end+1] if start != -1 and end != -1 else resp_text

                result_data = json.loads(clean_json)
                
                total_cal, total_p, total_c, total_f = 0, 0, 0, 0
                final_items = []
                
                for item in result_data.get("items", []):
                    portion = item.get("portion", 1.0)
                    if item.get("crId"):
                        hpb_data = fetch_hpb_details(item["crId"])
                        if hpb_data:
                            total_cal += round(hpb_data["calories"] * portion)
                            total_p += round(hpb_data["protein"] * portion)
                            total_c += round(hpb_data["carbs"] * portion)
                            total_f += round(hpb_data["fat"] * portion)
                            final_items.append({"name": item["name"], "portion": portion})
                            continue
                    
                    total_cal += round(item.get("est_cal", 0) * portion)
                    total_p += round(item.get("est_p", 0) * portion)
                    total_c += round(item.get("est_c", 0) * portion)
                    total_f += round(item.get("est_f", 0) * portion)
                    final_items.append({"name": item["name"], "portion": portion})

                for f in processed_temp_files:
                    if os.path.exists(f):
                        try: os.remove(f)
                        except: pass

                return (result_data.get("food_summary", "Unknown"), total_cal, total_p, total_c, total_f, final_items)

            except Exception as e:
                last_error = e
                if "429" in str(e):
                    print(f"Key {k_idx} + Model {m_name} hit rate limit, trying next permutation...")
                    continue
                else:
                    # If it's a 404 or something else, try next model/key
                    print(f"Non-429 error with {m_name}: {e}")
                    continue

    print(f"Pipeline Error after trying ALL keys and models: {last_error}")
    return "Unknown", 0, 0, 0, 0, []

    print(f"Pipeline Error after trying all keys: {last_error}")
    return "Unknown", 0, 0, 0, 0, []

def generate_daily_summary(meals_list, target_calories):
    """
    Generates a human-friendly summary acting as a nutrition coach.
    """
    if not meals_list:
        return "No data recorded for today."

    configure_genai()
    model = genai.GenerativeModel('gemini-2.0-flash-lite')
    
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
    except Exception as e:
        print(f"Error generating daily summary: {e}")
        return None
