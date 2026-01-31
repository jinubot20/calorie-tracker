import requests
import json
import sqlite3
import os
import math
import logging
import google.generativeai as genai
from dotenv import load_dotenv

import re

load_dotenv()

# Configuration
DB_PATH = "calorie_tracker.db"

def parse_portion_unit(portion_str):
    """Parses strings like '1 plate(s) = 418g' to extract the unit."""
    if not portion_str or portion_str == "-":
        return "unit"
    clean = portion_str.replace("(s)", "").strip()
    match = re.search(r'\d+\s+(.*?)\s*=', clean)
    if match:
        return match.group(1).strip()
    parts = clean.split()
    if parts and not parts[0].isdigit():
        return parts[0]
    if len(parts) > 1:
        return parts[1]
    return "unit"

# API Key Rotation Logic
PRIMARY_KEY = os.getenv("GOOGLE_API_KEY")
SECONDARY_KEY = os.getenv("GOOGLE_API_KEY_2")

def get_rotating_key():
    """Simple toggle between two keys based on a counter file or random."""
    if not SECONDARY_KEY:
        return PRIMARY_KEY
    
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
            SELECT h.name, h.crId, h.description, e.embedding, h.default_unit, h.default_weight
            FROM hpb_foods h 
            JOIN hpb_embeddings e ON h.crId = e.crId
        """)
        rows = cursor.fetchall()
        conn.close()
        
        # 3. Rank by similarity
        scored_items = []
        for name, crId, desc, emb_json, unit, weight in rows:
            emb = json.loads(emb_json)
            score = cosine_similarity(query_vec, emb)
            scored_items.append({
                "name": name, 
                "crId": crId, 
                "desc": desc, 
                "score": score,
                "unit": unit or "unit",
                "weight": weight or 0
            })
            
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
            raw_portion = data.get("defaultPortion", "")
            return {
                "calories": round(nutrients.get("energy", 0)),
                "protein": round(nutrients.get("protein", 0)),
                "carbs": round(nutrients.get("carbohydrate", 0)),
                "fat": round(nutrients.get("fat", 0)),
                "unit": parse_portion_unit(raw_portion)
            }
    except Exception as e:
        print(f"Error fetching HPB details for {crId}: {e}")
    return None

def estimate_calories(image_paths: list = None, user_description: str = None):
    # Model Rotation Pool: We'll try the best ones first
    MODELS_TO_TRY = [
        'gemini-2.0-flash-lite',
        'gemini-flash-latest',
        'gemini-pro-latest'
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
                
                # TASK 1: Identification & Label Detection
                id_prompt = f"""
                Analyze this meal photo and description.
                
                TASK 1: DETECTION
                Identify every distinct food item and drink. 
                STRICT SUBJECT RULES:
                1. PRIMARY ONLY: Focus ONLY on the items that are the main subject.
                2. IGNORE EDGES/CROPPED: Omit items at edges or partially cut off.
                
                TASK 2: NUTRITION LABEL DETECTION
                Check if there is a clear, legible Nutrition Information Panel (NIP) or Food Label visible in the photo that specifies calories/macros for the primary item.
                
                {desc_part}
                
                Respond in the following format:
                LABEL_FOUND: [YES/NO]
                ITEMS: [Comma-separated list of items]
                """
                
                response = model.generate_content([id_prompt] + contents)
                text = response.text.strip()
                
                label_found = False
                identified_items = []
                
                for line in text.split('\n'):
                    if "LABEL_FOUND:" in line:
                        label_found = "YES" in line.upper()
                    if "ITEMS:" in line:
                        identified_items = [x.strip() for x in line.split("ITEMS:")[1].split(",")]
                
                # If identifying items failed via format, fallback to previous simple logic
                if not identified_items:
                    if '\n' in text:
                        identified_items = [x.strip() for x in text.split('\n')][-1].split(',')
                    else:
                        identified_items = [x.strip() for x in text.split(',')]

                # OPTION A: DIRECT EXTRACTION FROM LABEL
                if label_found:
                    print("Nutrition Label detected! Switching to Direct Extraction mode...")
                    extract_prompt = f"""
                    You are a nutrition expert. A clear food label has been detected in this image.
                    
                    USER DESCRIPTION: {user_description}
                    
                    TASK:
                    1. Read the nutrition label in the image.
                    2. Extract: Calories, Protein, Carbs, and Fat.
                    3. Calculate the total based on the quantity consumed mentioned in the description (if any).
                    
                    Return JSON:
                    {{
                      "food_summary": "Name of Product on Label",
                      "calories": 0,
                      "protein": 0,
                      "carbs": 0,
                      "fat": 0,
                      "items": [
                        {{
                          "name": "Item from Label", 
                          "portion": 1.0,
                          "cal": 0,
                          "p": 0,
                          "c": 0,
                          "f": 0
                        }}
                      ]
                    }}
                    """
                    extract_resp = model.generate_content([extract_prompt] + contents)
                    extract_text = extract_resp.text.strip()
                    
                    # JSON extraction
                    if '```json' in extract_text:
                        clean_json = extract_text.split('```json')[1].split('```')[0].strip()
                    else:
                        start = extract_text.find('{')
                        end = extract_text.rfind('}')
                        clean_json = extract_text[start:end+1] if start != -1 and end != -1 else extract_text
                    
                    res = json.loads(clean_json)
                    return (
                        res.get("food_summary", "Label Detected"),
                        res.get("calories", 0),
                        res.get("protein", 0),
                        res.get("carbs", 0),
                        res.get("fat", 0),
                        res.get("items", [])
                    )

                # OPTION B: STANDARD 2-PASS PIPELINE
                # Pass 2: Candidate Retrieval (Semantic Search)
                all_matches = []
                for item in identified_items:
                    candidates = get_semantic_candidates(item, limit=10)
                    # Clean candidates for the prompt to keep it small but include units
                    clean_candidates = [
                        {"name": c["name"], "crId": c["crId"], "unit": c.get("unit", "unit"), "desc": c["desc"]}
                        for c in candidates
                    ]
                    all_matches.append({"query": item, "candidates": clean_candidates})

                # Pass 3: Grounded Judging & Portions
                judge_prompt = f"""
                You are a nutrition expert matching real meals to an official database.
                
                Original User Description: {user_description}
                Identified Items: {", ".join(identified_items)}
                
                For each item identified, look at the photo (if provided) and pick the best match from the provided HPB candidates.
                
                CRITICAL INSTRUCTION FOR ACCURACY:
                1. USER TEXT PRIORITY: If the user mentions a quantity or portion (e.g., "5 pieces", "half", "1 slice", "shared"), you MUST use that instead of the visual.
                2. UNIT CONVERSION RULE: If the user specifies a quantity in a small unit (e.g., "tablespoon", "teaspoon", "scoop") but the HPB candidate unit is larger (e.g., "cup", "bowl", "plate"), you MUST calculate the portion as a fraction.
                   - Example: "4 tablespoons" of yoghurt vs "1 small cup (150g)" -> portion is ~0.4.
                   - NEVER return a huge multiplier (like 68.0) for a single bowl/cup item unless the user explicitly says they ate 68 bowls.
                3. UNIT AWARENESS: Look at the "unit" field for each candidate. If the unit is "plate" and the user has a small side portion, adjust portion to 0.3 or similar.
                3. THE "BISCUIT" RULE: For Cream Crackers or Biscuits, the HPB database standard is 1 PIECE. If a user says "5 pieces", you MUST set portion to 5.0.
                4. NO IMAGE RULE: If NO images are provided, assume standard serving (portion: 1.0) for identified items UNLESS a quantity is specified in the text.
                5. THE "SLICE" RULE: Items like "Ngoh Hiang" or "Fish Cake" are often defined as a WHOLE ROLL. If the user mentions a "SLICE", adjust portion to ~0.1 - 0.2.
                6. THE "DAB" RULE: For condiments like Sambal, Chili, or Soy Sauce, if it is a small side portion (e.g. in a plastic saucer or on the side), adjust portion to ~0.1 (approx 10-15 kcal). Do not treat it as a main dish.
                7. STRICT PRIMARY FOCUS: Strictly OMIT any items that are at the edges, corners, or partially cropped out of the frame. Focus only on the central, intended subject of the meal.
                8. PORTION SCALING: 1.0 = standard serving, 0.5 = half, 1.5 = large. Lean toward 1.0 for health-conscious users unless cues are obvious.
                
                HPB CANDIDATES:
                {json.dumps(all_matches)}
                
                If an item has NO reasonable match in the list, set "crId" to null and provide your own best estimate for macros and a standard "unit".
                
                Return JSON:
                {{
                  "food_summary": "Overall Meal Name",
                  "items": [
                    {{"name": "Item Name", "crId": "FXXXX", "portion": 1.0, "unit": "unit", "est_cal": 0, "est_p": 0, "est_c": 0, "est_f": 0}}
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
                            final_items.append({
                                "name": item["name"], 
                                "portion": portion,
                                "unit": hpb_data.get("unit", "unit"),
                                "cal": round(hpb_data["calories"]),
                                "p": round(hpb_data["protein"]),
                                "c": round(hpb_data["carbs"]),
                                "f": round(hpb_data["fat"])
                            })
                            continue
                    
                    total_cal += round(item.get("est_cal", 0) * portion)
                    total_p += round(item.get("est_p", 0) * portion)
                    total_c += round(item.get("est_c", 0) * portion)
                    total_f += round(item.get("est_f", 0) * portion)
                    final_items.append({
                        "name": item["name"], 
                        "portion": portion,
                        "unit": item.get("unit", "unit"),
                        "cal": round(item.get("est_cal", 0)),
                        "p": round(item.get("est_p", 0)),
                        "c": round(item.get("est_c", 0)),
                        "f": round(item.get("est_f", 0))
                    })

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
                    print(f"Non-429 error with {m_name}: {e}")
                    continue

    print(f"Pipeline Error after trying ALL keys and models: {last_error}")
    return "Unknown", 0, 0, 0, 0, []

def generate_daily_summary(meals_list, target_calories):
    """Generates a human-friendly summary acting as a nutrition coach with retry logic."""
    if not meals_list:
        return "No data recorded for today."

    # Use Matrix Rotation for summaries too
    MODELS_TO_TRY = [
        'gemini-2.0-flash-lite',
        'gemini-flash-latest',
        'gemini-pro-latest'
    ]
    
    keys_to_try = [0, 1] if SECONDARY_KEY else [0]
    current_key_idx = 0 if get_rotating_key() == PRIMARY_KEY else 1
    if current_key_idx == 1:
        keys_to_try = [1, 0]

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
    Keep the note brief (3-4 sentences), encouraging, and professional.
    """

    last_error = None
    for k_idx in keys_to_try:
        configure_genai(k_idx)
        for m_name in MODELS_TO_TRY:
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(prompt)
                return response.text.strip()
            except Exception as e:
                last_error = e
                print(f"Summary generation error with Key {k_idx} and Model {m_name}: {e}")
                continue

    print(f"Final Summary error after trying all: {last_error}")
    return None
