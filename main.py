import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# உங்கள் Render-ல் இருக்கும் ENV விபரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_live_price(security_id):
    """
    தனுஷ் v2 LTP API-க்கான மிக எளிய மற்றும் வலுவான அணுகுமுறை
    """
    url = f"https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN,
        'client-id': CLIENT_ID,
        'Content-Type': 'application/json'
    }
    
    # தனுஷ் v2-ல் NSE_FNO கீயுடன் சரியான ஆப்ஜெக்ட் ஸ்ட்ரக்சர்
    payload = {
        "NSE_FNO": [{"securityId": str(security_id)}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # லாக்ஸில் வரும் டேட்டாவை வைத்து நாம் அடுத்த கட்டத்திற்குச் செல்லலாம்
            print(f"DEBUG DATA: {data}")
            return data
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Critical Exception: {e}")
    return None

if __name__ == "__main__":
    print("V17.0 Initialized...")
    # டெஸ்டிங்கிற்காக SBIN செக்யூரிட்டி ஐடி 814 ஐ மட்டும் முயற்சிப்போம்
    get_live_price("814")
    
    # ஆப் எக்ஸிட் ஆகாமல் இருக்க...
    while True:
        time.sleep(60)
