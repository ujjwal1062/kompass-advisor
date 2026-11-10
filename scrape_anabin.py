import os
import glob
import pandas as pd
import requests
import time
import json

# The AJAX endpoint used by Anabin's search
BASE_URL = "http://anabin.kmk.org/index.php"

# --- CONFIG ---
# Path to your INCOMPLETE CSV (to get the list of university names)
FOLDER_PATH = r"D:\dont delete ujjwal\dataset\indian_university_dataset\Indian_University_Registry_Package\data"
# Output file for the new, accurate data
OUTPUT_CSV = "anabin_official_india.csv"

def get_anabin_status(university_name):
    """Queries the Anabin AJAX endpoint for a given university name."""
    params = {
        "eID": "user_anabin_institutionen",
        "conf": "institutionsergebnisliste",
        "sEcho": "1",
        "iColumns": "13",
        "iDisplayStart": "0",
        "iDisplayLength": "10",
        "bRegex": "false",
        "iSortingCols": "1",
        "iSortCol_0": "2",
        "sSortDir_0": "asc",
        "s1": university_name,
        "iDataIds": "1"
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Anabin returns a nested list. We look for the first exact match.
        if data.get("aaData"):
            for entry in data["aaData"]:
                # entry[2] is the university name, entry[5] is the status
                if entry[2].lower().strip() == university_name.lower().strip():
                    return entry[5] # e.g., 'H+', 'H+/-', 'H-'
        return "Not Found"
    except Exception as e:
        print(f"  [Error] {university_name}: {e}")
        return "Error"

def scrape_all():
    # 1. Read the list of universities from your existing CSV
    files = glob.glob(os.path.join(FOLDER_PATH, "*.csv"))
    if not files:
        print("❌ Original CSV not found.")
        return
    
    df = pd.read_csv(files[0])
    university_names = df['institution_name'].dropna().unique()
    print(f"Found {len(university_names)} universities to check. This will take a few minutes...")

    # 2. Scrape the real status for each one
    results = []
    for i, name in enumerate(university_names):
        print(f"[{i+1}/{len(university_names)}] Checking: {name}...")
        status = get_anabin_status(name)
        results.append({
            "institution_name": name,
            "official_anabin_status": status
        })
        # Be polite to the server to avoid getting blocked
        time.sleep(0.5) 

    # 3. Save the new, accurate CSV
    new_df = pd.DataFrame(results)
    new_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n🎉 Done! Saved accurate data for {len(results)} universities to {OUTPUT_CSV}")

if __name__ == "__main__":
    scrape_all()