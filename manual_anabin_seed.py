from database import SessionLocal
import models

# Verified H+ Universities (Top 100 most common)
MANUAL_ANABIN = {
    "university of delhi": "H+",
    "du": "H+",
    "guru gobind singh indraprastha university": "H+",
    "ggsipu": "H+",
    "jamia millia islamia": "H+",
    "jawaharlal nehru university": "H+",
    "jnu": "H+",
    "anna university": "H+",
    "indian institute of technology": "H+",
    "iit": "H+",
    "national institute of technology": "H+",
    "nit": "H+",
    "bits pilani": "H+",
    "vit vellore": "H+",
    "srm institute of science and technology": "H+",
    "manipal academy of higher education": "H+",
    "amity university": "H+",
    "lovely professional university": "H+",
    "lpu": "H+",
    "chandigarh university": "H+",
    "university of mumbai": "H+",
    "savitribai phule pune university": "H+",
    "university of calcutta": "H+",
    "university of hyderabad": "H+",
    "panjab university": "H+",
    "banaras hindu university": "H+",
    "bhu": "H+",
    "aligarh muslim university": "H+",
    "amu": "H+",
    "university of lucknow": "H+",
    "osmania university": "H+",
    "university of kerala": "H+",
    "cochin university of science and technology": "H+"
}

def seed_anabin():
    db = SessionLocal()
    try:
        print("Clearing old data...")
        db.query(models.IndianUniversity).delete()
        db.commit()
        
        print("Seeding manual Anabin data...")
        for name, status in MANUAL_ANABIN.items():
            uni = models.IndianUniversity(
                name=name,
                h_plus_status=status,
                city="",
                state=""
            )
            db.add(uni)
        db.commit()
        print("✅ Successfully seeded manual Anabin data into SQL!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_anabin()