from database import SessionLocal
import models

db = SessionLocal()
# Look for GGSIPU or Indraprastha
results = db.query(models.IndianUniversity).filter(
    models.IndianUniversity.name.ilike("%Indraprastha%")
).all()

if not results:
    print("❌ The university is NOT in the database. The ingestion failed.")
else:
    for r in results:
        print(f"Name: {r.name} | H+ Status: {r.h_plus_status}")
db.close()