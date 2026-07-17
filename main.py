import os
import requests
import threading
import pandas as pd
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

# CSV-லிருந்து Security ID எடுக்கும் பங்க்ஷன்
def get_security_id_from_csv(strike, option_type):
    try:
        df = pd.read_csv('api-scrip-master-detailed.csv', low_memory=False)
        
        # ஸ்ட்ரைக் மற்றும் ஆப்ஷன் டைப் இரண்டையும் சரியாக பில்டர் செய்கிறோம்
        # '800' ஆக இருக்கலாம் என்பதால் int(strike) என்று மாற்றுகிறேன்
        filtered = df[(df['STRIKE_PRICE'] == int(strike)) & (df['SYMBOL_NAME'].str.contains(option_type))]
        
        if not filtered.empty:
            return str(filtered['SECURITY_ID'].iloc[0])
        else:
            print(f"DEBUG: Security ID not found for {strike} {option_type}")
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
    # உதாரணத்திற்கு 800 ஸ்ட்ரைக்
    ce_id = get_security_id_from_csv(1000.0, "CE")
    pe_id = get_security_id_from_csv(1000.0, "PE")
    
    if not ce_id or not pe_id:
        print("Security ID not found for strike 1000!")
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
        print(f"📈 CE Price (1000): {ce_price} | 📉 PE Price (1000): {pe_price}")
    else:
        print("API Error:", response.text)

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    while True:
        try:
            fetch_data()
        except Exception as e:
            print(f"Error in main loop: {e}")
        time.sleep(60) # 1 நிமிடம் இடைவெளி
