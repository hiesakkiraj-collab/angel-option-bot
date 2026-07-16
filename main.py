import os
import time
import requests
import pandas as pd
import io

# ரகசிய விபரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_dhan_instruments():
    """
    தனுஷ் இன்ஸ்ட்ருமென்ட் மாஸ்டரை டவுன்லோடு செய்து, 
    எக்ஸ்சேஞ்ச் ஐடிக்குரிய Dhan Security ID-ஐ மேப் செய்யும்.
    """
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        df = pd.read_csv(io.StringIO(response.text))
        # SBIN க்கான ஐடியை மட்டும் தேடுவோம்
        sbin_data = df[df['SEM_TRADING_SYMBOL'].str.contains("SBIN", na=False)]
        print(f"SBIN மேப்பிங் விபரங்கள்:\n{sbin_data[['SEM_TRADING_SYMBOL', 'SEM_SMST_SECURITY_ID']]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("V19.0 Worker Mode Started...")
    get_dhan_instruments()
    
    # லூப்பில் ஓடாமல் இருக்க சிறிய இடைவெளி
    time.sleep(10)
    print("Worker task completed.")
