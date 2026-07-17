import os
import time
import requests
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

# Render Environment Variables-ல் இருந்து விபரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

# 📡 1. Render போர்ட் பைண்டிங் (Port Binding) செய்வதற்கான வெப் சர்வர்
# இது "No open ports detected" என்ற எர்ரர் வராமல் பார்த்துக் கொள்ளும்
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('', port)
    
    class MyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"SBI ATM Option Bot is running successfully!")
        def log_message(self, format, *args):
            pass  # லாக்ஸ் சுத்தமாக இருக்க சர்வர் லாக்ஸை தவிர்க்கிறோம்
            
    try:
        httpd = HTTPServer(server_address, MyHandler)
        print(f"📡 Web server started on port {port} (Render Port Binding Active)")
        httpd.serve_forever()
    except Exception as e:
        print(f"⚠️ Web server error: {e}")

# 📊 2. SBI-ன் ATM CE மற்றும் PE ஆப்ஷன் விலைகளை எடுக்கும் பங்க்ஷன்
def fetch_sbi_atm_options():
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    # SBIN (3045) Equity Option Chain Request
    payload = {
        "underlyingScri": 55263,  # SBI-ன் சரியான Underlying Security ID இதுவாகத்தான் இருக்கும்
        "underlyingSeg": "NSE_EQ"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            resp_json = response.json()
            data = resp_json.get("data", {})
            
            # 1. Underlying Spot Price (SBI தற்போதைய விலை) கண்டறிதல்
            underlying_price = data.get("underlyingPrice") or data.get("spotPrice") or data.get("lastPrice")
            option_chain = data.get("oc") or data.get("optionChain") or data.get("data") or []
            
            if not underlying_price and option_chain:
                # ஒருவேளை நேரடியாக இல்லாவிட்டால், முதல் ஆப்ஷனில் இருந்து எடுக்க முயற்சிப்போம்
                underlying_price = option_chain[0].get("lastPrice")
            
            # 2. ATM (At The Money) ஸ்ட்ரைக் விலையைக் கணக்கிடுதல்
            if underlying_price and option_chain:
                closest_contract = None
                min_diff = float('inf')
                
                # ஸ்பாட் விலைக்கு மிக அருகில் இருக்கும் ஸ்ட்ரைக்கை தேடுகிறது
                for contract in option_chain:
                    strike = contract.get("strikePrice") or contract.get("strike_price")
                    if strike is not None:
                        diff = abs(float(strike) - float(underlying_price))
                        if diff < min_diff:
                            min_diff = diff
                            closest_contract = contract
                
                if closest_contract:
                    atm_strike = closest_contract.get("strikePrice") or closest_contract.get("strike_price")
                    ce_data = closest_contract.get("ce") or closest_contract.get("CE") or {}
                    pe_data = closest_contract.get("pe") or closest_contract.get("PE") or {}
                    
                    ce_ltp = ce_data.get("lastPrice") or ce_data.get("ltp")
                    pe_ltp = pe_data.get("lastPrice") or pe_data.get("ltp")
                    
                    print("-" * 50)
                    print(f"📈 SBI Spot Price: {underlying_price}")
                    print(f"🎯 Calculated ATM Strike: {atm_strike}")
                    print(f"🟢 ATM CALL (CE) LTP: {ce_ltp}")
                    print(f"🔴 ATM PUT (PE) LTP: {pe_ltp}")
                    print("-" * 50)
                else:
                    print("⚠️ Could not calculate ATM strike from the option chain list.")
            else:
                print(f"⚠️ Empty Option Chain or Spot Price. Raw Data: {resp_json}")
                
        else:
            print(f"❌ Dhan API FAILED with status {response.status_code}")
            print("RAW RESPONSE:", response.text)
            
    except Exception as e:
        print(f"❌ Error while fetching Option Chain: {e}")

if __name__ == "__main__":
    print("🚀 Starting Dhan ATM Option Tracker Bot...")
    
    # 1. Render போர்ட் எர்ரர் வராமல் இருக்க வெப் சர்வரை பேக்கிரவுண்டில் இயக்குகிறோம்
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # 2. ஒவ்வொரு 10 விநாடிக்கும் மார்க்கெட் டேட்டாவை எடுக்கும் மெயின் லூப்
    while True:
        try:
            fetch_sbi_atm_options()
            # Dhan API ரேட் லிமிட்டை தவிர்க்க 10 விநாடிகள் இடைவெளி
            time.sleep(10)
        except KeyboardInterrupt:
            print("🛑 Bot stopped by user.")
            break
        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            time.sleep(10)
