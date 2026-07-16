import os
import time
import requests
import pandas as pd
import io

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_dhan_ltp_fixed():
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    response = requests.get(url, timeout=30)
    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    
    # SBIN-Jul2026-FUT க்கான ஐடியில் எது சிறியதோ அதை எடுப்போம் (Internal ID)
    sbin_fut = df[(df['SEM_TRADING_SYMBOL'] == "SBIN-Jul2026-FUT")]
    # சிறிய ID-ஐத் தேடுகிறோம்
    target_id = str(sbin_fut['SEM_SMST_SECURITY_ID'].min())
    print(f"DEBUG: Selected Internal ID for SBIN-FUT: {target_id}")
    
    # தனுஷ் v2 LTP API Call
    api_url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    payload = {"NSE_FNO": [{"securityId": target_id}]}
    
    resp = requests.post(api_url, headers=headers, json=payload)
    print(f"RESPONSE: {resp.text}")

if __name__ == "__main__":
    get_dhan_ltp_fixed()
    
