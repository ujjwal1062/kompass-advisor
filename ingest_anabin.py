import os
import pandas as pd
from database import SessionLocal, engine
import models

# Ensure new tables are created
models.Base.metadata.create_all(bind=engine)

# Path to the NEW, scraped CSV
CSV_PATH = "anabin_official_india.csv"

def ingest_anabin():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: {CSV_PATH} not found. Please run scrape_anabin.py first.")
        return

    print(f"✅ Found file: {CSV_PATH}")
    db = SessionLocal()
    try:
        df = pd.read_csv(CSV_PATH)
        
        # Wipe old data to prevent duplicates
        db.query(models.IndianUniversity).delete()
        db.commit()
        print("Cleared old Anabin data. Loading fresh, accurate data...")
        
        count = 0
        for index, row in df.iterrows():
            name = row.get('institution_name')
            status = row.get('official_anabin_status')
            if not name or pd.isna(name): continue
            
            uni = models.IndianUniversity(
                name=str(name).strip(),
                h_plus_status=str(status).strip(),
                city="", # We don't have city data from the scrape
                state=""
            )
            db.add(uni)
            count += 1
            if count % 100 == 0:
                db.commit()
                
        db.commit()
        print(f"🎉 Successfully ingested {count} Indian universities into SQL!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_anabin()