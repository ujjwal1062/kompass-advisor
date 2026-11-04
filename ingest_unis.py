import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import re

# Ensure tables exist
models.Base.metadata.create_all(bind=engine)

def clean_float(val):
    if pd.isna(val): return None
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).replace(',', '.')
    match = re.search(r'\d+(?:\.\d+)?', val_str)
    return float(match.group()) if match else None

def clean_int(val):
    if pd.isna(val): return None
    if isinstance(val, (int, float)): return int(val)
    match = re.search(r'\d+', str(val))
    return int(match.group()) if match else None

def get_val(row, possible_cols):
    for col in possible_cols:
        if col in row and not pd.isna(row[col]) and str(row[col]).strip() != "":
            return str(row[col]).strip()
    return None

def ingest_data():
    db = SessionLocal()
    try:
        csv_path = r"D:\dont delete ujjwal\dataset\university dataset\raw\German_Universities_All_Datasets_Master.csv"
        
        print("Reading CSV (this takes a few seconds)...")
        df = pd.read_csv(csv_path, low_memory=False)
        
        # 1. Extract University Names and remove empty rows
        df['uni_name'] = df.apply(lambda row: get_val(row, ['university', 'University', 'university_name']), axis=1)
        df = df.dropna(subset=['uni_name'])
        
        print(f"Found {len(df)} valid rows. Extracting universities...")
        
        # 2. Insert Universities (Bulk)
        unique_unis = df['uni_name'].unique()
        existing_unis = {u.official_name: u.id for u in db.query(models.University.id, models.University.official_name).all()}
        new_unis = []
        
        for uni_name in unique_unis:
            if uni_name not in existing_unis:
                uni_row = df[df['uni_name'] == uni_name].iloc[0]
                new_unis.append(models.University(
                    official_name=uni_name,
                    city=get_val(uni_row, ['city', 'study_location']),
                    federal_state=get_val(uni_row, ['state']),
                    institution_type=get_val(uni_row, ['institution_type', 'university_type']),
                    rank=clean_int(get_val(uni_row, ['QS_2027_global_rank', 'qs_2027_global_rank', 'QS_global_rank', 'QS_world_ranking_2027', 'QS_2027_Germany_position'])),
                    official_url=get_val(uni_row, ['official_source', 'official_study_portal'])
                ))
        
        if new_unis:
            db.add_all(new_unis)
            db.commit()
            print(f"✅ Added {len(new_unis)} new universities.")
        
        # Refresh map of existing universities to get their new database IDs
        existing_unis = {u.official_name: u.id for u in db.query(models.University.id, models.University.official_name).all()}
        
        # 3. Insert Programs (Bulk)
        print("Extracting programs...")
        new_progs = []
        seen_progs = set()
        
        for index, row in df.iterrows():
            prog_name = get_val(row, ['programme_name', 'Programme'])
            if not prog_name: continue
                
            uni_id = existing_unis[row['uni_name']]
            
            # Use a python set to check for duplicates in memory (Super Fast!)
            prog_key = f"{uni_id}_{prog_name}"
            if prog_key in seen_progs: continue
            seen_progs.add(prog_key)
                
            new_progs.append(models.Program(
                university_id=uni_id,
                title=prog_name,
                degree_type=get_val(row, ['degree_type', 'Degree', 'degree_level']),
                field_of_study=get_val(row, ['field_of_study', 'field', 'faculty_or_area']),
                language=get_val(row, ['language', 'teaching_language', 'language_of_instruction', 'Language']),
                tuition_fee_eur=clean_float(get_val(row, ['tuition_fee', 'Tuition/Fees', 'general_tuition_fee'])),
                semester_contribution_eur=clean_float(get_val(row, ['semester_contribution', 'semester_fee', 'semester_contribution_winter_2026_27'])),
                duration_semesters=clean_int(get_val(row, ['standard_duration', 'duration', 'regular_duration'])),
                official_program_url=get_val(row, ['programme_url', 'official_programme_url'])
            ))
            
            # Commit in batches of 2000 to prevent memory crashes
            if len(new_progs) >= 2000:
                db.add_all(new_progs)
                db.commit()
                print(f"Committed {len(new_progs)} programs...")
                new_progs = []
                
        # Commit remaining
        if new_progs:
            db.add_all(new_progs)
            db.commit()
            
        print("🎉 Ingestion Complete! Database is fully populated.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_data()