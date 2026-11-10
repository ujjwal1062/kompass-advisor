import os
import glob
import pandas as pd
from database import SessionLocal, engine
import models

# Ensure new tables are created
models.Base.metadata.create_all(bind=engine)

# Path to your Indian university dataset
FOLDER_PATH = r"D:\dont delete ujjwal\dataset\indian_university_dataset\Indian_University_Registry_Package\data"

def ingest_anabin():
    search_pattern = os.path.join(FOLDER_PATH, "*.csv")
    files = glob.glob(search_pattern)
    
    if not files:
        print(f"❌ Error: Could not find any CSV files in {FOLDER_PATH}")
        return

    target_file = files[0]
    print(f"✅ Found file: {target_file}")
    
    db = SessionLocal()
    try:
        df = pd.read_csv(target_file)
        print(f"Loaded {len(df)} rows. Inserting into SQL...")
        
        count = 0
        for index, row in df.iterrows():
            # Using .get() with multiple fallbacks to handle different column naming conventions
            name = row.get('University Name') or row.get('institution_name') or row.get('Name') or row.get('institution')
            if not name or pd.isna(name): continue
            
            uni = models.IndianUniversity(
                name=str(name).strip(),
                h_plus_status=str(row.get('H+ Status') or row.get('status') or row.get('H+') or 'Not listed').strip(),
                city=str(row.get('City') or row.get('city') or '').strip(),
                state=str(row.get('State') or row.get('state') or '').strip()
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