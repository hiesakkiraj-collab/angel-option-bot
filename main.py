import os
import requests
import threading
import pandas as pd
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_security_id_from_csv(strike, option_type):
    try:
        df = pd.read_csv('api-scrip-master-detailed.csv', low_memory=False)
        
        # ஸ்ட்ரைக் விலையை இன்டிஜராக மாற்றுகிறோம்
        target_strike = int(strike)
        
        # லாக்ஸில் என்ன நடக்கிறது என்று பார்க்க ஒரு பிரிண்ட்
        print(f"DEBUG: Searching for Strike={target_strike}, Type={option_type}")
        
        # CSV-ல் தேடுகிறோம்
        filtered = df[(df['STRIKE_PRICE'] == target_strike) & (df['SYMBOL_NAME'].str.contains(option_type))]
        
        if not filtered.empty:
            found_id = str(filtered['SECURITY_ID'].iloc[0])
            print(f"DEBUG: Found ID: {found_id}")
            return found_id
        else:
            # ஒருவேளை கிடைக்கவில்லை என்றால் என்ன இருக்கிறது என்று பார்க்க
            print(f"DEBUG: No data found for {target_strike} {option_type}")
            return None
    except Exception as e:
        print(f"Error in CSV reading: {e}")
        return None

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    class MyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
    HTTPServer(('', port), MyHandler).serve_forever()

def fetch_data():
    # 800 ஸ்ட்ரைக் விலைக்காகத் தேடுகிறோம்
    ce_id = get_security_id_from_csv(800, "CE")
    pe_id = get_security_id_from_csv(800, "PE")
    
    if not ce_id or not pe_id:
        print("Security ID missing. Check Debug logs above!")
        return

    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    payload = {
        "symbols": [
            {"exchangeSegment": "NSE_FNO", "securityId": ce_id},
            {"exchangeSegment": "NSE_FNO", "securityId": pe_id}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json().get("data", {})
        ce_price = data.get(ce_id, {}).get("ltp")
        pe_price = data.get(pe_id, {}).get("ltp")
        print(f"✅ SUCCESS: CE Price: {ce_price} | PE Price: {pe_price}")
    else:
        print("API Error:", response.text)

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    while True:
        try:
            fetch_data()
        except Exception as e:
            print(f"Error in main loop: {e}")
        time.sleep(60)
