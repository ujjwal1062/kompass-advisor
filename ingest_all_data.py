import os
import pandas as pd
import time
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal, engine
import models

load_dotenv()
models.Base.metadata.create_all(bind=engine)

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# The root folder where all your Master datasets are stored
BASE_DIR = r"D:\dont delete ujjwal\dataset"

def get_embedding(text):
    """Gets the vector embedding from FreeLLMAPI with error handling"""
    text = str(text)[:8000] # Truncate to avoid token limits
    response = client.embeddings.create(
        input=[text],
        model="auto"
    )
    return response.data[0].embedding

def process_csv_file(file_path, topic_name):
    db = SessionLocal()
    try:
        print(f"\n📂 Reading: {file_path}")
        df = pd.read_csv(file_path)
        
        # Skip empty files
        if df.empty:
            print("   Empty file, skipping.")
            return

        # Check how many rows are already in the DB for this specific file to avoid duplicates
        existing_count = db.query(models.PolicyDocument).filter(
            models.PolicyDocument.source_file == os.path.basename(file_path)
        ).count()
        
        if existing_count >= len(df):
            print("   Already fully ingested, skipping.")
            return

        # Convert the whole dataframe to a list of strings (one per row)
        rows_to_process = df.head(50) # Limiting to 50 rows per file for now to avoid hitting API rate limits
        
        for index, row in rows_to_process.iterrows():
            # Combine all columns into one text string
            row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
            
            # Skip very short/empty rows
            if len(row_text) < 20:
                continue
                
            try:
                vector = get_embedding(row_text)
                
                doc = models.PolicyDocument(
                    topic=topic_name,
                    source_file=os.path.basename(file_path),
                    chunk_text=row_text,
                    embedding=vector
                )
                db.add(doc)
                db.commit()
                print(f"   ✅ Embedded row {index + 1}/{len(rows_to_process)}")
                
                # Sleep briefly to respect API rate limits
                time.sleep(0.5) 
                
            except Exception as api_err:
                print(f"   ⚠️ API Error on row {index+1}: {api_err}")
                time.sleep(2) # wait longer if there's an error
                db.rollback()
                
    except Exception as e:
        print(f"   ❌ File Error: {e}")
    finally:
        db.close()

def crawl_and_ingest():
    print("🚀 Starting Universal Data Ingestion...")
    
    # The specific folders from your screenshots
    target_folders = {
        "01_Application_APS": "Application & APS",
        "02_Language_Examinations": "Language Requirements",
        "03_Finance_Affordability": "Finance & Costs",
        "04_Visa_Immigration": "Visa & Immigration",
        "05_Arrival_Accommodation_Everyday_Life": "Arrival & Life",
        "Student Employment, Internships & Careers": "Careers & Work",
        "German_Studienkolleg_Course_Requirements": "Studienkolleg",
        "Indian_Class12_Subject_Master": "Indian Education",
        "Indian_Bachelor_Degree_Catalogue": "Indian Education"
    }

    # Loop through the base directory to find these folders
    for root, dirs, files in os.walk(BASE_DIR):
        for folder_name, topic_name in target_folders.items():
            if folder_name in root:
                for file in files:
                    if file.endswith(".csv") and "validation" not in file.lower():
                        file_path = os.path.join(root, file)
                        process_csv_file(file_path, topic_name)

    print("\n🎉 ALL DATA INGESTED SUCCESSFULLY!")

if __name__ == "__main__":
    crawl_and_ingest()