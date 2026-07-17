import os
import requests

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_live_data_v2():
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # 🎯 தனுஷ் v2-ன் தற்போதைய சரியான பார்மட்: 'symbols' கீயைப் பயன்படுத்த வேண்டும்
    payload = {
        "symbols": [
            {
                "exchangeSegment": "NSE_EQ",
                "securityId": "3045"
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"ULTIMATE SUCCESS RESPONSE: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_live_data_v2()
