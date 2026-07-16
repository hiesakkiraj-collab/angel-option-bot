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

STOCKS_LIST = ["SBIN", "RELIANCE"]

STRIKE_GAPS = {
    "SBIN": 10,
    "RELIANCE": 20,
    "NIFTY": 50,
    "BANKNIFTY": 100
}

# பேக்கப் தோராய விலைகள் (ஸ்கேன் செய்யத் துவங்கும் தற்போதைய மார்க்கெட் ரேஞ்ச்)
STOCK_APPROX_PRICES = {
    "SBIN": 770,      # தற்போதைய SBIN தோராய விலை
    "RELIANCE": 1740,  # தற்போதைய RELIANCE தோராய விலை
    "NIFTY": 24200,
    "BANKNIFTY": 52500
}

DHAN_MASTER_DF = None
COL_TOKEN = None       
COL_INST_NAME = None   
COL_TRADING_SYM = None 
COL_STRIKE = None      
COL_EXPIRY = None

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
# 2. Dhan Master Scrip டவுன்லோடு & பில்டரிங்
# ------------------------------------------
def download_dhan_scrip_master():
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_EXPIRY
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
            for col in all_cols:
                if col in ["SEM_SMST_SECURITY_ID", "SMST_SECURITY_ID", "SECURITY_ID"]:
                    COL_TOKEN = col
                elif col in ["SEM_INSTRUMENT_NAME", "INSTRUMENT", "INSTRUMENT_NAME"]:
                    COL_INST_NAME = col
                elif col in ["SEM_TRADING_SYMBOL", "SYMBOL_NAME", "TRADING_SYMBOL"]:
                    COL_TRADING_SYM = col
                elif col in ["SEM_STRIKE_PRICE", "STRIKE_PRICE"]:
                    COL_STRIKE = col
                elif col in ["SEM_EXPIRY_DATE", "EXPIRY_DATE"]:
                    COL_EXPIRY = col

            if not COL_TOKEN: COL_TOKEN = "SEM_SMST_SECURITY_ID"
            if not COL_INST_NAME: COL_INST_NAME = "SEM_INSTRUMENT_NAME"
            if not COL_TRADING_SYM: COL_TRADING_SYM = "SEM_TRADING_SYMBOL"
            if not COL_STRIKE: COL_STRIKE = "SEM_STRIKE_PRICE"
            if not COL_EXPIRY: COL_EXPIRY = "SEM_EXPIRY_DATE"

            print("✅ Master CSV Columns Mapped Successfully.")
            return True
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 3. Live LTP API Call (🔥 NFO செக்மெண்ட்டிற்கு மாற்றப்பட்டுள்ளது)
# ------------------------------------------
def get_dhan_live_ltp(security_id, segment="NFO"):
    if not ACCESS_TOKEN or not CLIENT_ID or not security_id:
        return 0.0
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {"instruments": [{"exchangeSegment": segment, "securityId": str(security_id)}]}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("data", data.get("Data", {}))
            return float(resp_data.get(str(security_id), {}).get("ltp", 0.0))
    except Exception: pass
    return 0.0

# ------------------------------------------
# 4. நியூ ஃபார்முலா கணக்கீடு லாஜிக்
# ------------------------------------------
def process_stock_strategy(stock):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_EXPIRY
    if DHAN_MASTER_DF is None: return

    try:
        gap = STRIKE_GAPS.get(stock, 10)
        gap_limit = gap / 2
        
        spot_price = STOCK_APPROX_PRICES.get(stock, 1000.0)
        inst_type = "OPTIDX" if stock in ["NIFTY", "BANKNIFTY"] else "OPTSTK"
        
        # 1. குறிப்பிட்ட ஸ்டாக் மற்றும் இன்ஸ்ட்ருமென்ட் பில்டர்
        df_stock = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[COL_INST_NAME] == inst_type) &
            (DHAN_MASTER_DF[COL_TRADING_SYM].str.startswith(stock.upper(), na=False))
        ].copy()
        
        df_stock[COL_STRIKE] = pd.to_numeric(df_stock[COL_STRIKE], errors='coerce')
        df_stock = df_stock.dropna(subset=[COL_STRIKE])
        
        # தற்போதைய எக்ஸ்பைரி கான்டராக்ட்களை மட்டும் எடுக்க பில்டர் (ஆப்ஷனை மட்டும் துல்லியமாக எடுக்க)
        if COL_EXPIRY in df_stock.columns and not df_stock[COL_EXPIRY].empty:
            df_stock = df_stock.sort_values(by=COL_EXPIRY)
        
        unique_strikes = sorted(df_stock[COL_STRIKE].unique())
        closest_strikes = sorted(unique_strikes, key=lambda x: abs(x - spot_price))[:12]
        closest_strikes = sorted(closest_strikes)
        
        selected_strike = None
        selected_call_ltp = 0.0
        selected_put_ltp = 0.0
        call_put_diff = 0.0
        
        # 🤝 STEP 1 & 2: கண்டிஷனை திருப்தி செய்யும் முதல் ஸ்ட்ரைக்கை தேடுதல்
        for strike in closest_strikes:
            df_strike = df_stock[df_stock[COL_STRIKE] == strike]
            
            call_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("CE", na=False)]
            put_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("PE", na=False)]
            
            if call_row.empty or put_row.empty: continue
            
            c_id = int(call_row.iloc[0][COL_TOKEN])
            p_id = int(put_row.iloc[0][COL_TOKEN])
            
            # 🔥 'NFO' செக்மெண்டில் செக் செய்கிறோம்
            c_ltp = get_dhan_live_ltp(c_id, segment="NFO")
            p_ltp = get_dhan_live_ltp(p_id, segment="NFO")
            
            if c_ltp == 0.0 or p_ltp == 0.0:
                continue
            
            diff = abs(c_ltp - p_ltp)
            
            if diff <= gap_limit:
                selected_strike = strike
                selected_call_ltp = c_ltp
                selected_put_ltp = p_ltp
                call_put_diff = diff
                break
                
        # பாதுகாப்பு பின்தொடர்தல் (ஒருவேளை மிகக் குறைந்த வித்தியாசம் இருந்தால்)
        if selected_strike is None:
            min_diff = 999999
            for strike in closest_strikes:
                df_strike = df_stock[df_stock[COL_STRIKE] == strike]
                call_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("CE", na=False)]
                put_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("PE", na=False)]
                if call_row.empty or put_row.empty: continue
                c_ltp = get_dhan_live_ltp(int(call_row.iloc[0][COL_TOKEN]), segment="NFO")
                p_ltp = get_dhan_live_ltp(int(put_row.iloc[0][COL_TOKEN]), segment="NFO")
                if c_ltp == 0.0 or p_ltp == 0.0: continue
                diff = abs(c_ltp - p_ltp)
                if diff < min_diff:
                    min_diff = diff
                    selected_strike = strike
                    selected_call_ltp = c_ltp
                    selected_put_ltp = p_ltp
                    call_put_diff = diff

        if selected_strike is None:
            print(f"❌ {stock}: Live FO data returned 0.0. Market closed or token error.")
            return

        # 🤝 STEP 3: சராசரி மற்றும் ரவுண்டிங்
        avg_ltp = (selected_call_ltp + selected_put_ltp) / 2
        rounded_value = round(avg_ltp / gap) * gap
        if rounded_value == 0: rounded_value = gap
        
        # 🤝 STEP 4: Call / Put Strike கணக்கீடு
        call_strike = selected_strike - rounded_value
        put_strike = selected_strike + rounded_value
        
        # 🤝 STEP 5: Adjusted Value கணக்கீடு
        if selected_put_ltp > selected_call_ltp:
            adjusted_value = selected_strike - call_put_diff
        else:
            adjusted_value = selected_strike + call_put_diff
            
        # 🤝 STEP 6: Triggers கணக்கீடு
        ce_stop_trigger = adjusted_value - call_strike
        pe_stop_trigger = put_strike - adjusted_value
        buy_trigger = rounded_value * 2
        
        # 📈 டெலிகிராம் அட்டவணை ரிப்போர்ட்
        report_msg = f"📊 **STRATEGY REPORT: {stock}**\n" \
                     f"Base Strike Checked: {int(selected_strike)} | Gap: {gap}\n" \
                     f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n" \
                     f"`Parameter        | Value`\n" \
                     f"`⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯`\n" \
                     f"`Call Strike      | {int(call_strike)}`\n" \
                     f"`Put Strike       | {int(put_strike)}`\n" \
                     f"`CE Stop Trigger  | {ce_stop_trigger:.2f}`\n" \
                     f"`PE Stop Trigger  | {pe_stop_trigger:.2f}`\n" \
                     f"`Buy Trigger      | {int(buy_trigger)}`\n" \
                     f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n" \
                     f"📞 _Live CE LTP: {selected_call_ltp} | PE LTP: {selected_put_ltp}_"
                     
        send_telegram(report_msg)
        print(f"✅ Processed successfully for {stock}")
        
    except Exception as e:
        print(f"Error processing strategy for {stock}: {e}")

def monitor_live_market():
    for stock in STOCKS_LIST:
        process_stock_strategy(stock)
        time.sleep(2)

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    time.sleep(2)
    
    if download_dhan_scrip_master():
        send_telegram("🟢 Multi-Stock Bot Activated (V14.2 - Fix LTP Live)!")
        
    while True:
        now_ist = datetime.now(IST).time()
        market_start = datetime(2000, 1, 1, 9, 15, 0).time()
        market_end = datetime(2000, 1, 1, 15, 30, 0).time()
        
        if market_start <= now_ist <= market_end:
            monitor_live_market()
            time.sleep(60)
        else:
            monitor_live_market()
            time.sleep(300)
