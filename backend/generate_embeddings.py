import google.generativeai as genai
import sqlite3
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

# Configuration
DB_PATH = "calorie_tracker.db"
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_and_store_embeddings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get items that don't have embeddings yet
    cursor.execute("""
        SELECT h.crId, h.name || ' ' || COALESCE(h.description, '')
        FROM hpb_foods h
        LEFT JOIN hpb_embeddings e ON h.crId = e.crId
        WHERE e.embedding IS NULL
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("All items already have embeddings.")
        return

    print(f"Generating embeddings for {len(rows)} items...")
    
    # Process in batches of 100
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=texts,
                task_type="retrieval_document"
            )
            
            embeddings = result['embedding']
            
            for crId, emb in zip(ids, embeddings):
                # Store as JSON string or binary blob. JSON is easier to debug for now.
                cursor.execute("INSERT INTO hpb_embeddings (crId, embedding) VALUES (?, ?)", 
                             (crId, json.dumps(emb)))
            
            conn.commit()
            print(f"  Processed {i + len(batch)}/{len(rows)}...")
            time.sleep(1) # Rate limit cushion
            
        except Exception as e:
            print(f"  Error in batch: {e}")
            time.sleep(5)
            
    conn.close()
    print("✓ Embedding generation complete.")

if __name__ == "__main__":
    generate_and_store_embeddings()
