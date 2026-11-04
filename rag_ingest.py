import os
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal, engine
import models

load_dotenv()
models.Base.metadata.create_all(bind=engine)

# Initialize FreeLLMAPI
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

def get_embedding(text):
    """Gets the vector embedding from FreeLLMAPI"""
    # Truncate text just in case a row is insanely long
    text = text[:8000] 
    response = client.embeddings.create(
        input=[text],
        model="auto"
    )
    return response.data[0].embedding

def ingest_rag_data():
    db = SessionLocal()
    try:
        # The exact path you provided, pointing directly to the CSV file
        csv_path = r"D:\dont delete ujjwal\dataset\GERMANY_STUDENT_JOURNEY_MASTER\04_Visa_Immigration\Germany_Student_Visa_Immigration_Master_Package\Germany_Student_Visa_Immigration_Master\data\rag_visa_answer_guardrails.csv"
        
        if not os.path.exists(csv_path):
            print(f"❌ Error: Cannot find {csv_path}. Please check the path.")
            return

        print("Reading RAG data...")
        df = pd.read_csv(csv_path)
        
        # For testing, let's just do the first 20 rows so it doesn't take too long
        df = df.head(20)
        
        print(f"Found {len(df)} rows. Generating embeddings (this will take a minute)...")
        
        for index, row in df.iterrows():
            # Combine all columns into one text block for the AI to read
            row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
            
            print(f"Processing row {index + 1}/{len(df)}...")
            try:
                vector = get_embedding(row_text)
                
                doc = models.PolicyDocument(
                    topic="Visa & Immigration",
                    source_file="rag_visa_answer_guardrails.csv",
                    chunk_text=row_text,
                    embedding=vector
                )
                db.add(doc)
                db.commit()
            except Exception as api_err:
                print(f"⚠️ Skipping row {index+1} due to API error: {api_err}")
                db.rollback()
            
        print("✅ RAG Data Ingestion Complete! Your AI now has specific visa rules.")

    except Exception as e:
        db.rollback()
        print(f"❌ Fatal Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_rag_data()