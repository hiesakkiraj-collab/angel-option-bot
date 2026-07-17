import os
import requests
import pandas as pd
import io

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_sbin_ltp():
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # தனுஷ் v2-ன் சரியான ஸ்ட்ரக்சர் இதுதான்:
    # 1. NSE_FNO கீ
    # 2. லிஸ்ட் உள்ளே டிப்ஷனரி
    # 3. securityId என்பது ஒரு ஸ்ட்ரிங்
    payload = {
        "NSE_FNO": [{"securityId": "1136312"}] 
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"RESPONSE: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_sbin_ltp()
