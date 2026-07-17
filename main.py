import os
import requests
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import pandas as pd

# API விவரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

# சர்வர் ஸ்டார்ட் செய்ய
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    class MyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is active!")
    httpd = HTTPServer(('', port), MyHandler)
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# CSV-லிருந்து ID எடுக்க
def get_security_id_from_csv(strike, option_type):
    try:
        df = pd.read_csv('api-scrip-master-detailed.csv', low_memory=False)
        target_strike = int(strike)
        filtered = df[(df['STRIKE_PRICE'] == target_strike) & (df['SYMBOL_NAME'].str.contains(option_type))]
        if not filtered.empty:
            return str(filtered['SECURITY_ID'].iloc[0])
        return None
    except Exception as e:
        print(f"CSV Error: {e}")
        return None

# மார்க்கெட் டேட்டா எடுக்க
def fetch_closed_price():
    ce_id = get_security_id_from_csv(1000, "CE")
    pe_id = get_security_id_from_csv(1000, "PE")
    
    if not ce_id or not pe_id:
        print("Security ID not found!")
        return

    url = "https://api.dhan.co/quotes/snfe"
    # Content-Type மற்றும் பிற ஹெடர்களைச் சரியாகச் சேர்த்துள்ளேன்
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    payload = {
        "symbols": [
            {"exchangeSegment": "NSE_FNO", "securityId": ce_id},
            {"exchangeSegment": "NSE_FNO", "securityId": pe_id}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        # ரெஸ்பான்ஸ் ஸ்டேட்டஸைப் பார்ப்போம்
        if response.status_code == 200:
            data = response.json().get("data", {})
            ce_price = data.get(ce_id, {}).get("lastPrice")
            pe_price = data.get(pe_id, {}).get("lastPrice")
            print(f"📊 CLOSED PRICE: CE(1000): {ce_price} | PE(1000): {pe_price}")
        else:
            # பிழை ஏற்பட்டால் என்ன மெசேஜ் வருகிறது என்று பார்ப்போம்
            print(f"API Error Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Connection Error: {e}")

# மெயின் லூப்
print("Bot started, waiting for market data...")
while True:
    fetch_closed_price()
    time.sleep(60)
