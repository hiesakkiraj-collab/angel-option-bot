import os
import requests

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_dhan_ltp_fixed():
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # இம்முறை: 
    # 1. NSE_FO கீயைப் பயன்படுத்துவோம்
    # 2. securityId-ஐ int ஆக மாற்றுவோம்
    payload = {
        "NSE_FO": [{"securityId": 1136312}] 
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"FINAL RESPONSE: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_dhan_ltp_fixed()
