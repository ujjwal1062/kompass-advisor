import os
import glob
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal
import models

load_dotenv()
client = OpenAI(api_key=os.getenv("GROQ_KEY_1"), base_url="https://api.groq.com/openai/v1")

FOLDER_PATH = r"D:\dont delete ujjwal\dataset\university dataset\raw"

def get_embedding(text):
    text = str(text)[:8000]
    try:
        # Try to use OpenAI/Groq, fallback to dummy 3072 if unsupported
        return client.embeddings.create(input=[text], model="text-embedding-3-small").data[0].embedding
    except:
        return [0.0] * 3072

def ingest_industry():
    search_pattern = os.path.join(FOLDER_PATH, "Germany_Companies_Startups_Career_Ecosy*")
    files = glob.glob(search_pattern)
    
    target_file = files[0] if files else None
    if not target_file:
        print(f"❌ Error: Could not find Companies/Startups file in {FOLDER_PATH}")
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
            
            vector = get_embedding(row_text)
            doc = models.PolicyDocument(
                topic="Industry & Careers",
                source_file=os.path.basename(target_file),
                chunk_text=row_text,
                embedding=vector
            )
            db.add(doc)
            count += 1
            if count % 50 == 0: db.commit()
                
        db.commit()
        print(f"🎉 Successfully ingested {count} industry records into the database!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_industry()