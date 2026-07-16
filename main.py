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
# 1. ரகசிய விபரங்கள் (Render Environment Variables)
# ==========================================
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STOCKS_LIST = ["SBIN"]
STOCK_APPROX_PRICES = {"SBIN": 1030}
STRIKE_GAPS = {"SBIN": 10}

PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

# காலம் பெயர்கள்
COL_TOKEN = None       
COL_INST_NAME = None   
COL_TRADING_SYM = None 
COL_STRIKE = None      
COL_OPTION_TYPE = None 

IST = timezone(timedelta(hours=5, minutes=30))

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ------------------------------------------
# 3. Dhan Master Scrip டவுன்லோடு
# ------------------------------------------
def download_dhan_scrip_master():
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_OPTION_TYPE
    print("Downloading Dhan Scrip Master File... Please wait...")
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data, low_memory=False, encoding='utf-8-sig')
            
            df.columns = df.columns.str.strip().str.upper()
            DHAN_MASTER_DF = df
            print("Dhan Scrip Master Downloaded Successfully!")
            
            all_cols = list(df.columns)
            print(f"📋 Available Columns in CSV: {all_cols[:10]}") # முதல் 10 காலம்களை லாகில் காட்டும்
            
            for col in all_cols:
                if col in ["SEM_EXM_EXCH_ID", "EXCH_ID", "SMART_TOKEN", "SEM_SMART_TOKEN", "SECURITY_ID"]:
                    COL_TOKEN = col
                elif col in ["SEM_INSTRUMENT_NAME", "INSTRUMENT", "INSTRUMENT_NAME"]:
                    COL_INST_NAME = col
                elif col in ["SEM_TRADING_SYMBOL", "SYMBOL_NAME", "TRADING_SYMBOL", "SYMBOL"]:
                    COL_TRADING_SYM = col
                elif col in ["SEM_STRIKE_PRICE", "STRIKE_PRICE"]:
                    COL_STRIKE = col
                elif col in ["SEM_OPTION_TYPE", "OPTION_TYPE"]:
                    COL_OPTION_TYPE = col

            if not COL_TOKEN: COL_TOKEN = all_cols[0]
            if not COL_INST_NAME: COL_INST_NAME = all_cols[1]
            if not COL_TRADING_SYM: COL_TRADING_SYM = all_cols[2]
            if not COL_STRIKE: COL_STRIKE = all_cols[3]
            if not COL_OPTION_TYPE: COL_OPTION_TYPE = all_cols[4]

            print(f"✅ Mapped -> Token: {COL_TOKEN}, Inst: {COL_INST_NAME}, Strike: {COL_STRIKE}, Symbol: {COL_TRADING_SYM}, OptionType: {COL_OPTION_TYPE}")
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Debugging Mode Option Details
# ------------------------------------------
def get_dhan_option_details(stock_name, target_strike, option_type):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_OPTION_TYPE
    if DHAN_MASTER_DF is None:
        return None, 0.0, target_strike
    
    try:
        # 🔥 DEBUGGING: மாஸ்டர் பைலில் இருக்கும் முதல் 5 ரோக்களின் மதிப்புகளை அப்படியே பிரிண்ட் செய்கிறோம்
        print("\n🔍 --- DEBUG: PRINTING FIRST 5 ROWS OF MASTER CSV ---")
        sample_df = DHAN_MASTER_DF[[COL_INST_NAME, COL_TRADING_SYM, COL_OPTION_TYPE, COL_STRIKE, COL_TOKEN]].head(5)
        print(sample_df.to_string())
        
        # 🔥 DEBUGGING: 'OPTSTK' அல்லது 'OPTIDX' ஏதாச்சும் பைலில் இருக்கா என்று செக் செய்கிறோம்
        unique_insts = DHAN_MASTER_DF[COL_INST_NAME].dropna().unique()
        print(f"🔍 Unique Instrument Names found in CSV: {list(unique_insts)[:10]}")
        
        # 🔥 DEBUGGING: 'SBIN' என்ற வார்த்தை எதிலாவது இருக்கிறதா என்று செக் செய்கிறோம்
        sbin_sample = DHAN_MASTER_DF[DHAN_MASTER_DF[COL_TRADING_SYM].str.contains('SBIN', na=False, case=False)].head(3)
        if not sbin_sample.empty:
            print("🔍 Found SBIN samples in CSV:")
            print(sbin_sample[[COL_INST_NAME, COL_TRADING_SYM, COL_OPTION_TYPE, COL_STRIKE]].to_string())
        else:
            print("❌ 'SBIN' word NOT FOUND ANYWHERE in Trading Symbol column!")
        print("---------------------------------------------------\n")

        # ஒரிஜினல் ஃபில்டர் லாஜிக்
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[COL_TRADING_SYM].str.startswith(stock_name.upper(), na=False)) &
            (DHAN_MASTER_DF[COL_OPTION_TYPE].str.upper() == option_type.upper())
        ].copy()
        
        if df_filter.empty:
            print(f"⚠️ Filter empty for {stock_name} {option_type}")
            return None, 0.0, target_strike

        df_filter[COL_STRIKE] = pd.to_numeric(df_filter[COL_STRIKE], errors='coerce')
        df_filter[COL_TOKEN] = pd.to_numeric(df_filter[COL_TOKEN], errors='coerce')
        df_filter = df_filter.dropna(subset=[COL_TOKEN, COL_STRIKE])
        
        target_strike_float = float(target_strike)
        df_filter['STRIKE_DIFF'] = (df_filter[COL_STRIKE] - target_strike_float).abs()
        df_sorted = df_filter.sort_values(by='STRIKE_DIFF')
        
        if not df_sorted.empty:
            security_id = int(df_sorted.iloc[0][COL_TOKEN])
            strike_found = float(df_sorted.iloc[0][COL_STRIKE])
            trading_symbol_found = str(df_sorted.iloc[0][COL_TRADING_SYM])
            return security_id, 0.0, strike_found
            
    except Exception as e:
        print(f"Error in debug finder: {e}")
    return None, 0.0, target_strike

# ------------------------------------------
# 5. Live LTP API Call 
# ------------------------------------------
def get_dhan_live_ltp(security_id):
    if not ACCESS_TOKEN or not CLIENT_ID or not security_id:
        return 0.0
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {"instruments": [{"exchangeSegment": "NSE_FO", "securityId": str(security_id)}]}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("data", data.get("Data", {}))
            return float(resp_data.get(str(security_id), {}).get("ltp", 0.0))
    except Exception: pass
    return 0.0

def run_pre_market_logic():
    print("Running Pre-Market Analysis for SBIN...")
    global PRE_MARKET_SELECTED_STRIKES
    target_strike = STOCK_APPROX_PRICES["SBIN"]
    call_id, _, call_strike = get_dhan_option_details("SBIN", target_strike, "CE")
    put_id, _, put_strike = get_dhan_option_details("SBIN", target_strike, "PE")
    
    if call_id and put_id:
        PRE_MARKET_SELECTED_STRIKES["SBIN"] = {"selected_strike": call_strike, "call_security_id": call_id, "put_security_id": put_id}
        print(f"✅ Setup Locked for SBIN: Strike {call_strike}")
    else:
        print(f"❌ Could not find SBIN contracts.")

def monitor_live_market():
    if not PRE_MARKET_SELECTED_STRIKES:
        run_pre_market_logic()
        return
    print("Checking Live Market Formula...")

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    time.sleep(2)
    if download_dhan_scrip_master():
        run_pre_market_logic()
    while True:
        monitor_live_market()
        time.sleep(60)
