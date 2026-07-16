import os
import time
import requests
import pandas as pd
import io
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading

# ==========================================
# ரகசிய விபரங்கள் (Render Environment Variables)
# ==========================================
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STOCKS_LIST = ["SBIN", "RELIANCE"]

# ------------------------------------------
# Dhan Master Scrip டவுன்லோடு & மேப்பிங்
# ------------------------------------------
def download_dhan_scrip_master():
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_EXPIRY
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data, low_memory=False, encoding='utf-8-sig')
            df.columns = df.columns.str.strip().str.upper()
            
            # 🎯 V15.9 திருத்தம்: தனுஷ் மார்க்கெட் ஃபீட் பெரும்பாலும் 'SEM_SMST_SECURITY_ID' ஐ ஏற்கும்
            # நாம் இப்போது மாஸ்டர் பைலில் உள்ள அனைத்து ஐடி காலம்களையும் லாக் செய்வோம்
            print(f"DEBUG: Columns Found: {list(df.columns)}")
            
            # தனுஷ் v2-க்கு ஏற்ற செக்யூரிட்டி ஐடி காலம்
            global DHAN_MASTER_DF
            DHAN_MASTER_DF = df
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

# ------------------------------------------
# 🔥 V15.9 Detector Engine (Token Test)
# ------------------------------------------
def get_ltp_with_validation(instruments_list):
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    
    # தனுஷ் v2-ல் NSE_FO-விற்குப் பதிலாக 'instruments' என்ற கீயையும் முயற்சிக்கலாம்
    token_objects = [{"securityId": str(item[0])} for item in instruments_list]
    payload = {"NSE_FO": token_objects}
    
    try:
        # நாம் அனுப்பும் முதல் 5 டோக்கன்களை மட்டும் சோதிப்போம்
        response = requests.post(url, headers=headers, json=payload, timeout=7)
        print(f"📡 [DEBUG V15.9 VALIDATOR]: Status {response.status_code} | Body: {response.text[:200]}")
        
        # பதில் வெற்றி பெற்றால் மட்டுமே LTP எடுக்கும்
        if response.status_code == 200:
            return response.json().get("data", {})
    except Exception as e:
        print(f"Detector Error: {e}")
    return {}

# ------------------------------------------
# இதர லாஜிக் பகுதி (பழையபடியே)
# ------------------------------------------
def monitor_live_market():
    # இந்த பகுதியில் process_stock_strategy-ல் V15.9 Detector-ஐ அழையுங்கள்
    # மாஸ்டர் CSV-ல் 'SEM_SMST_SECURITY_ID' தான் சரியான ஐடியாக இருக்க வேண்டும்.
    # ஒருவேளை அது வேலை செய்யவில்லை என்றால் 'SEM_TOKEN' ஐ முயலவும்.
    pass

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    download_dhan_scrip_master()
    # லாக்ஸில் வரும் Columns பட்டியலை எனக்கு அனுப்புங்கள்!
    while True:
        time.sleep(60)
