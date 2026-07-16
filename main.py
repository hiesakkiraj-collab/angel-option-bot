import os
import requests
import pandas as pd
import io

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_dhan_ltp_fixed():
    # SBIN EQ (Equity) ஐடி 3045
    target_id = "3045"
    
    api_url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    
    # 🎯 Payload-ஐ வெறும் 'instruments' என்ற கீயில் மாற்றுவோம்
    payload = {
        "instruments": [{"securityId": target_id, "exchangeSegment": "NSE_EQ"}]
    }
    
    resp = requests.post(api_url, headers=headers, json=payload)
    print(f"RESPONSE FOR SBIN EQ: {resp.text}")

if __name__ == "__main__":
    get_dhan_ltp_fixed()
