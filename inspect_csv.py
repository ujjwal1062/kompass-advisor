import pandas as pd
import glob
import os

FOLDER_PATH = r"D:\dont delete ujjwal\dataset\indian_university_dataset\Indian_University_Registry_Package\data"
files = glob.glob(os.path.join(FOLDER_PATH, "*.csv"))

if files:
    df = pd.read_csv(files[0])
    status_counts = df['current_anabin_status'].value_counts(dropna=False)
    print("--- STATUS BREAKDOWN OF YOUR CSV ---")
    print(status_counts)
    
    print("\n--- TOP 20 'NOT CHECKED' UNIVERSITIES ---")
    not_checked = df[df['current_anabin_status'] == 'not_checked']['institution_name'].head(20).tolist()
    for uni in not_checked:
        print(f"- {uni}")