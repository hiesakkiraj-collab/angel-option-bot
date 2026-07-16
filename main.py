import os
import time
import requests
import pandas as pd
import io
from datetime import datetime, timedelta, timezone

# 1. ரகசிய விபரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

# 2. 🔥 V16.0 Token Resolver (DhanSecurityId Fix)
def get_dhan_batch_ltp_fixed(instruments_list):
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    
    # தனுஷ் v2-ன் ரகசிய கீ: 'dhanSecurityId'
    # சில பழைய மாஸ்டர் ஐடிகள் வேலை செய்யாது, ஆனால் இதுதான் சரியான வழி
    token_objects = [{"dhanSecurityId": str(item[0])} for item in instruments_list]
    
    payload = {
        "NSE_FNO": token_objects
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=7)
        print(f"📡 [DEBUG V16.0]: Status {response.status_code} | Body: {response.text[:200]}")
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
    return {}

# 3. Main Logic
if __name__ == "__main__":
    # டெஸ்ட் செய்ய ஒரு சிக்னல் (உதாரணத்திற்கு SBIN)
    # உங்களது பழைய கோடில் இருந்த அதே `batch_instruments` லிஸ்ட்டை இங்கே பயன்படுத்துங்கள்
    print("Running V16.0 Token Resolver...")
    # தற்காலிக டெஸ்ட்:
    # get_dhan_batch_ltp_fixed([(138995, "SBIN_TEST")])
