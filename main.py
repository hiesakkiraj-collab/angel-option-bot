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

# நீங்கள் கண்காணிக்க விரும்பும் ஸ்டாக்குகளின் பட்டியல்
STOCKS_LIST = ["SBIN", "RELIANCE"]

# ஒவ்வொரு பங்கிற்குமான Strike Gap
STRIKE_GAPS = {
    "SBIN": 10,
    "RELIANCE": 20,
    "NIFTY": 50,
    "BANKNIFTY": 100
}

# Dhan Equity/Index டோக்கன் ஐடிகள் (Spot Price கண்டறிய)
STOCK_UNDERLYING_TOKENS = {
    "SBIN": 3045,      
    "RELIANCE": 2885,  
    "NIFTY": 13,       
    "BANKNIFTY": 25
}

DHAN_MASTER_DF = None
COL_TOKEN = None       
COL_INST_NAME = None   
COL_TRADING_SYM = None 
COL_STRIKE = None      

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
# 2. Dhan Master Scrip டவுன்லோடு
# ------------------------------------------
def download_dhan_scrip_master():
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE
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

            if not COL_TOKEN: COL_TOKEN = "SEM_SMST_SECURITY_ID"
            if not COL_INST_NAME: COL_INST_NAME = "SEM_INSTRUMENT_NAME"
            if not COL_TRADING_SYM: COL_TRADING_SYM = "SEM_TRADING_SYMBOL"
            if not COL_STRIKE: COL_STRIKE = "SEM_STRIKE_PRICE"

            print("✅ Master CSV Columns Mapped Successfully.")
            return True
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 3. Live LTP API Call
# ------------------------------------------
def get_dhan_live_ltp(security_id, segment="NSE_FO"):
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
# 4. புதிய 7-படி ஃபார்முலா கணக்கீடு மற்றும் லைவ் செக்
# ------------------------------------------
def process_stock_strategy(stock):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE
    if DHAN_MASTER_DF is None: return

    try:
        gap = STRIKE_GAPS.get(stock, 10)
        gap_limit = gap / 2
        
        # Spot Price எடுத்து தற்போதைய ரேஞ்சை கண்டுபிடிக்கிறோம்
        underlying_token = STOCK_UNDERLYING_TOKENS.get(stock)
        segment = "NSE_EQ" if stock not in ["NIFTY", "BANKNIFTY"] else "IDX_I"
        spot_price = get_dhan_live_ltp(underlying_token, segment=segment)
        
        if spot_price == 0.0:
            print(f"⚠️ Could not fetch Live Spot Price for {stock}. Skipping iteration.")
            return
            
        inst_type = "OPTIDX" if stock in ["NIFTY", "BANKNIFTY"] else "OPTSTK"
        
        # தற்போதைய ஸ்பாட் விலைக்கு அருகில் இருக்கும் 7 ஸ்ட்ரைக்குகளை பில்டர் செய்கிறோம்
        df_stock = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[COL_INST_NAME] == inst_type) &
            (DHAN_MASTER_DF[COL_TRADING_SYM].str.startswith(stock.upper(), na=False))
        ].copy()
        
        df_stock[COL_STRIKE] = pd.to_numeric(df_stock[COL_STRIKE], errors='coerce')
        df_stock = df_stock.dropna(subset=[COL_STRIKE])
        
        # Spot விலைக்கு அருகிலுள்ள தனித்துவமான ஸ்ட்ரைக்குகள்
        unique_strikes = sorted(df_stock[COL_STRIKE].unique())
        closest_strikes = sorted(unique_strikes, key=lambda x: abs(x - spot_price))[:8]
        closest_strikes = sorted(closest_strikes)
        
        selected_strike = None
        selected_call_ltp = 0.0
        selected_put_ltp = 0.0
        call_put_diff = 0.0
        
        # 🤝 STEP 1: கண்டிஷனை திருப்தி செய்யும் முதல் ஸ்ட்ரைக்கை தேடுகிறோம்
        for strike in closest_strikes:
            df_strike = df_stock[df_stock[COL_STRIKE] == strike]
            
            call_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("CE", na=False)]
            put_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("PE", na=False)]
            
            if call_row.empty or put_row.empty: continue
            
            c_id = int(call_row.iloc[0][COL_TOKEN])
            p_id = int(put_row.iloc[0][COL_TOKEN])
            
            c_ltp = get_dhan_live_ltp(c_id)
            p_ltp = get_dhan_live_ltp(p_id)
            
            if c_ltp == 0.0 or p_ltp == 0.0: continue
            
            diff = abs(c_ltp - p_ltp)
            
            if diff <= gap_limit:
                # கண்டிஷன் ஓகே!
                selected_strike = strike
                selected_call_ltp = c_ltp
                selected_put_ltp = p_ltp
                call_put_diff = diff
                break
                
        if selected_strike is None:
            print(f"ℹ️ {stock}: No strike met the condition (Diff <= {gap_limit}) currently.")
            return

        # 🤝 STEP 3: சராசரி மற்றும் ரவுண்டிங்
        avg_ltp = (selected_call_ltp + selected_put_ltp) / 2
        rounded_value = round(avg_ltp / gap) * gap
        
        # rounded_value பூஜ்ஜியமாக இருந்தால் கணக்கீடு உடையாமல் இருக்க கேப் அளவுக்கு மாற்றுதல்
        if rounded_value == 0: rounded_value = gap
        
        # 🤝 STEP 4: Call / Put Strike கணக்கீடு
        call_strike = selected_strike - rounded_value
        put_strike = selected_strike + rounded_value
        
        # 🤝 STEP 5: Adjusted Value கணக்கீடு
        if selected_put_ltp > selected_call_ltp:
            adjusted_value = selected_strike - call_put_diff
        else:
            adjusted_value = selected_strike + call_put_diff
            
        # 🤝 STEP 6: Stop Triggers கணக்கீடு
        ce_stop_trigger = adjusted_value - call_strike
        pe_stop_trigger = put_strike - adjusted_value
        buy_trigger = rounded_value * 2
        
        # 📈 டெலிகிராமிற்கு அட்டவணை வடிவில் அனுப்பும் இறுதி ரிப்போர்ட்
        report_msg = f"📊 **STRATEGY REPORT: {stock}**\n" \
                     f"Spot Price: {spot_price:.2f} | Gap: {gap}\n" \
                     f"Selected Strike: {int(selected_strike)} (Diff: {call_put_diff:.2f})\n" \
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
        print(f"✅ Target processed and sent for {stock}")
        
    except Exception as e:
        print(f"Error processing strategy for {stock}: {e}")

# ------------------------------------------
# 5. லைவ் லூப் மற்றும் சர்வர் செட்டப்
# ------------------------------------------
def monitor_live_market():
    for stock in STOCKS_LIST:
        process_stock_strategy(stock)
        time.sleep(2) # API ஓவர்லோடு ஆகாமல் இருக்க சின்ன கேப்

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    time.sleep(2)
    
    if download_dhan_scrip_master():
        send_telegram("🟢 Multi-Stock Bot Activated with New 7-Step Logic!")
        
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
