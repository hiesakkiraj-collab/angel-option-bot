import os
import requests
import pandas as pd
import io

def inspect_columns():
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    response = requests.get(url, timeout=30)
    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    
    # SBIN EQ (3045) உள்ள வரிசையை மட்டும் பிரித்து, அதன் அனைத்து காலம்களையும் பிரிண்ட் செய்வோம்
    sbin_eq = df[df['SEM_SMST_SECURITY_ID'] == 3045]
    print("--- FULL DATA FOR SBIN EQ ---")
    for col in sbin_eq.columns:
        print(f"{col}: {sbin_eq.iloc[0][col]}")

if __name__ == "__main__":
    inspect_columns()
