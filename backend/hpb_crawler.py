import requests
import sqlite3
import time
import math
import logging

# Configuration
DB_PATH = "calorie_tracker.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://pphtpc.hpb.gov.sg/web/sgfoodid/tools/food-search"
}

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def init_hpb_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hpb_foods (
            id TEXT PRIMARY KEY,
            crId TEXT,
            name TEXT,
            description TEXT,
            category_l1 TEXT,
            category_l2 TEXT,
            type TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_items(items):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for item in items:
        cursor.execute("""
            INSERT OR REPLACE INTO hpb_foods (id, crId, name, description, category_l1, category_l2, type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get('id'),
            item.get('crId'),
            item.get('name'),
            item.get('description'),
            item.get('l1Category'),
            item.get('l2Category'),
            item.get('type')
        ))
    conn.commit()
    conn.close()

def fetch_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logging.error(f"Request failed: {e}")
        return None

def crawl_group(group_id=None, is_drink=False):
    base_url = "https://pphtpc.hpb.gov.sg/bff/v1/food-portal/foods"
    
    if is_drink:
        label = "Drinks"
        url_template = f"{base_url}?pageNumber={{page}}&type=Drink"
    else:
        label = f"Group {group_id}"
        url_template = f"{base_url}?pageNumber={{page}}&foodGroupId={group_id}"

    logging.info(f"Checking {label}...")
    
    # 1. Fetch first page to get totalCount
    data = fetch_page(url_template.format(page=1))
    if not data or len(data) == 0:
        logging.info(f"  {label} is empty. Skipping.")
        return

    total_count = data[0].get('totalCount', 0)
    if total_count == 0:
        return

    # 2. Calculate pages
    page_size = len(data)
    total_pages = math.ceil(total_count / page_size)
    logging.info(f"  Found {total_count} items across {total_pages} pages.")

    # 3. Save first page
    save_items(data)

    # 4. Crawl remaining pages
    for page in range(2, total_pages + 1):
        logging.info(f"    Fetching page {page}/{total_pages}...")
        page_data = fetch_page(url_template.format(page=page))
        if page_data:
            save_items(page_data)
        time.sleep(1) # Be nice to the server

def run_full_crawl():
    init_hpb_table()
    
    # Crawl Food Groups 0-28
    for gid in range(29):
        crawl_group(group_id=gid)
        time.sleep(1)

    # Crawl Drinks
    crawl_group(is_drink=True)
    
    logging.info("Crawler finished successfully!")

if __name__ == "__main__":
    run_full_crawl()
