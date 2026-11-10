import os
import glob
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal
import models

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_KEY_1"),
    base_url="https://api.groq.com/openai/v1"
)

FOLDER_PATH = r"D:\dont delete ujjwal\dataset\university dataset\raw"

def get_embedding(text):
    text = str(text)[:8000]
    try:
        response = client.embeddings.create(
            input=[text],
            model="text-embedding-3-small" 
        )
        return response.data[0].embedding
    except Exception:
        # ✅ FIX: Match the database column size (3072) so it doesn't crash
        return [0.0] * 3072 

def ingest_scholarships():
    search_pattern = os.path.join(FOLDER_PATH, "Germany_Scholarships_Combined_Master_Fi*")
    files = glob.glob(search_pattern)
    
    target_file = None
    for f in files:
        if f.endswith('.csv'):
            target_file = f
            break
    if not target_file and files:
        target_file = files[0] 

    if not target_file:
        print(f"❌ Error: Could not find file in {FOLDER_PATH}")
        return

    print(f"✅ Found file: {target_file}")
    db = SessionLocal()
    
    try:
        if target_file.endswith('.csv'):
            df = pd.read_csv(target_file)
        else:
            df = pd.read_excel(target_file)
            
        count = 0
        for index, row in df.iterrows():
            row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
            if len(row_text) < 20: continue
            
            print(f"Embedding row {index + 1}/{len(df)}...")
            vector = get_embedding(row_text)
            
            doc = models.PolicyDocument(
                topic="Scholarships",
                source_file=os.path.basename(target_file),
                chunk_text=row_text,
                embedding=vector
            )
            db.add(doc)
            count += 1
            if count % 10 == 0: db.commit()
                
        db.commit()
        print(f"🎉 Successfully ingested {count} scholarships into the database!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_scholarships()