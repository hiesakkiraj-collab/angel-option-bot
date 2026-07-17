import requests
import os

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_atm_option_data():
    url = "https://api.dhan.co/charts/v1/optionchain" # இதுதான் Chart API-க்கான சரியான எண்ட்-பாயிண்ட்
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # நீங்கள் கொடுத்த பார்மட் படி மாற்றப்பட்ட payload
    payload = {
        "exchangeSegment": "NSE_FNO", # ஆப்ஷன்ஸ் என்பதால் NSE_FNO
        "interval": "1",
        "securityId": 3045,          # SBIN-ன் Security ID
        "instrument": "STKOPT",      # ஸ்டாக் ஆப்ஷன் என்பதால் STKOPT
        "expiryFlag": "MONTH",
        "expiryCode": 1,
        "strike": "ATM",             # ATM டேட்டா
        "drvOptionType": "CALL",     # CALL அல்லது PUT
        "requiredData": ["open", "high", "low", "close", "oi"], 
        "fromDate": "2026-07-17",    # இன்றைய தேதி
        "toDate": "2026-07-17"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        print("✅ CHART API RESPONSE:", response.json())
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    get_atm_option_data()
