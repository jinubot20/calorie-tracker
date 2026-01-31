import requests
import sqlite3
import time
import re

DB_PATH = "calorie_tracker.db"
HPB_DETAILS_URL = "https://pphtpc.hpb.gov.sg/bff/v1/food-portal/foods/details/{crId}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def parse_portion_unit(portion_str):
    """
    Parses strings like '1 plate(s) = 418g' or '1 bowl(s) = 419g'
    to extract the unit ('plate', 'bowl', 'pcs', etc).
    """
    if not portion_str or portion_str == "-":
        return "unit"
    
    # Remove '1 ' at start and '(s)'
    clean = portion_str.replace("(s)", "").strip()
    # Match '1 unit = weight' or just 'unit'
    match = re.search(r'\d+\s+(.*?)\s*=', clean)
    if match:
        return match.group(1).strip()
    
    # Fallback: take first word if it's not a number
    parts = clean.split()
    if parts and not parts[0].isdigit():
        return parts[0]
    if len(parts) > 1:
        return parts[1]
        
    return "unit"

def enrich_hpb_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all foods that haven't been enriched yet
    cursor.execute("SELECT crId, name FROM hpb_foods WHERE default_unit IS NULL")
    rows = cursor.fetchall()
    
    if not rows:
        print("All items already enriched.")
        return

    print(f"Enriching {len(rows)} items with units and weights...")
    
    for i, (crId, name) in enumerate(rows):
        try:
            url = HPB_DETAILS_URL.format(crId=crId)
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                raw_portion = data.get("defaultPortion", "")
                weight = data.get("defaultWeight", 0)
                unit = parse_portion_unit(raw_portion)
                
                cursor.execute("""
                    UPDATE hpb_foods 
                    SET default_unit = ?, default_weight = ? 
                    WHERE crId = ?
                """, (unit, weight, crId))
                
                if i % 50 == 0:
                    conn.commit()
                    print(f"  Progress: {i}/{len(rows)} - Last: {name} ({unit})")
            
            # Tiny sleep to be polite to HPB API
            time.sleep(0.1)
            
        except Exception as e:
            print(f"  Error enriching {crId}: {e}")
            time.sleep(2)
            
    conn.commit()
    conn.close()
    print("✓ Enrichment complete.")

if __name__ == "__main__":
    enrich_hpb_data()
