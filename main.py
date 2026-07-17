import os
import requests

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_dhan_ltp_final():
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # 🎯 அனைத்து செக்மென்ட்டையும் ஒரே நேரத்தில் அனுப்பி டேட்டாவைப் பிடிப்போம்
    payload = {
        "NSE_FNO": [{"securityId": 1136312}],
        "NSE_FO": [{"securityId": 1136312}],
        "NSE_EQ": [{"securityId": 3045}],
        "BSE_EQ": [{"securityId": 3045}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"ULTIMATE RESPONSE: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_dhan_ltp_final()
