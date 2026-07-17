import requests
import pandas as pd
import io

def find_sbin_data():
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    response = requests.get(url)
    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    
    # SBIN என்ற வார்த்தை எந்தெந்த காலமில் இருக்கிறது என்று பார்ப்போம்
    print("Searching for 'SBIN' in all columns...")
    for col in df.columns:
        # SBIN என்ற வார்த்தை அந்த காலமில் இருக்கிறதா என்று பார்ப்போம்
        matches = df[df[col].astype(str).str.contains("SBIN", na=False)]
        if not matches.empty:
            print(f"Found match in column: {col}")
            # அந்த வரியின் முதல் 5 முடிவுகளை பிரிண்ட் செய்
            print(matches[[col, 'SEM_SMST_SECURITY_ID']].head())
            break

if __name__ == "__main__":
    find_sbin_data()
