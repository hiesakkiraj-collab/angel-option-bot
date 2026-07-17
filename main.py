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
        target_strike = int(strike)
        
        # 1000 ஸ்ட்ரைக் பிரைஸை தேடுகிறது
        filtered = df[(df['STRIKE_PRICE'] == target_strike) & (df['SYMBOL_NAME'].str.contains(option_type))]
        
        if not filtered.empty:
            return str(filtered['SECURITY_ID'].iloc[0])
        else:
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
    # இங்கே 1000 என்று மாற்றியுள்ளேன்
    ce_id = get_security_id_from_csv(1000, "CE")
    pe_id = get_security_id_from_csv(1000, "PE")
    
    if not ce_id or not pe_id:
        print("Security ID missing for 1000 strike!")
        return

    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    
    # integer ஆக மாற்றி அனுப்புகிறோம்
    payload = {
        "symbols": [
            {"exchangeSegment": "NSE_FNO", "securityId": int(ce_id)},
            {"exchangeSegment": "NSE_FNO", "securityId": int(pe_id)}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json().get("data", {})
        # integer key-வை வைத்து எடுக்கிறோம்
        ce_price = data.get(int(ce_id), {}).get("ltp")
        pe_price = data.get(int(pe_id), {}).get("ltp")
        print(f"✅ SUCCESS: CE Price (1000): {ce_price} | PE Price (1000): {pe_price}")
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
