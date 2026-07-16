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

STOCK_APPROX_PRICES = {
    "SBIN": 820.0,       
    "RELIANCE": 1650.0,  
    "NIFTY": 24200.0,
    "BANKNIFTY": 52500.0
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
# 2. Dhan Master Scrip டவுன்லோடு & மேப்பிங்
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
# 3. Batch Live LTP API Call 
# ------------------------------------------
def get_dhan_batch_ltp(instruments_list, segment="NSE_FO"):
    if not ACCESS_TOKEN or not CLIENT_ID or not instruments_list:
        return {}
        
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    
    payload = {
        "instruments": [
            {"exchangeSegment": str(segment), "securityId": str(item[0])}
            for item in instruments_list
        ]
    }
    
    result_map = {}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=7)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("data", data.get("Data", {}))
            for item in instruments_list:
                sec_id = str(item[0])
                ltp = float(resp_data.get(sec_id, {}).get("ltp", 0.0))
                result_map[int(sec_id)] = ltp
        else:
            print(f"❌ Batch HTTP Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Exception in Batch LTP Call: {e}")
    return result_map

# ------------------------------------------
# 4. நியூ ஃபார்முலா கணக்கீடு லாஜிக்
# ------------------------------------------
def process_stock_strategy(stock):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_TRADING_SYM, COL_STRIKE, COL_EXPIRY
    if DHAN_MASTER_DF is None: return

    try:
        gap = STRIKE_GAPS.get(stock, 10)
        gap_limit = gap / 2
        approx_base = STOCK_APPROX_PRICES.get(stock, 1000.0)
        
        inst_type = "OPTIDX" if stock in ["NIFTY", "BANKNIFTY"] else "OPTSTK"
        
        df_stock = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[COL_INST_NAME] == inst_type) &
            (DHAN_MASTER_DF[COL_TRADING_SYM].str.startswith(stock.upper(), na=False))
        ].copy()
        
        if df_stock.empty:
            print(f"❌ {stock}: No rows found in Master CSV.")
            return

        df_stock['PARSED_EXPIRY'] = pd.to_datetime(df_stock[COL_EXPIRY], errors='coerce')
        df_stock = df_stock.dropna(subset=['PARSED_EXPIRY'])
        
        today_now = datetime.now(IST).replace(tzinfo=None)
        today_date = pd.Timestamp(today_now.date())
        
        future_expiries = df_stock[df_stock['PARSED_EXPIRY'] >= today_date]
        if future_expiries.empty:
            print(f"❌ {stock}: No active future expiry dates found.")
            return
            
        current_expiry = future_expiries['PARSED_EXPIRY'].min()
        df_stock = df_stock[df_stock['PARSED_EXPIRY'] == current_expiry].copy()
        
        print(f"🔍 {stock}: Selected Current Expiry Date -> {current_expiry.strftime('%Y-%m-%d')}")

        df_stock[COL_STRIKE] = pd.to_numeric(df_stock[COL_STRIKE], errors='coerce')
        df_stock = df_stock.dropna(subset=[COL_STRIKE])
        
        # 🔥 [FIX] Dynamic Strike Price Checking
        # ஒருவேளை CSV-ல் ஸ்ட்ரைக் ப்ரைஸ் 100 மடங்கு அதிகமாக இருந்தால் (உதாரணம்: SBIN 82000 என்று இருந்தால்) மட்டும் வகுக்க வேண்டும்.
        # நேரடியாக 820 என்று இருந்தால் வகுக்கக் கூடாது.
        max_strike_in_df = df_stock[COL_STRIKE].max()
        if max_strike_in_df > (approx_base * 5):
            df_stock[COL_STRIKE] = df_stock[COL_STRIKE] / 100.0
            print(f"⚙️ {stock}: Strike prices divided by 100 dynamically.")

        unique_strikes = sorted(df_stock[COL_STRIKE].unique())
        closest_strikes = sorted(unique_strikes, key=lambda x: abs(x - approx_base))[:12]
        closest_strikes = sorted(closest_strikes)
        
        batch_instruments = []
        strike_pairs = {} 
        
        for strike in closest_strikes:
            df_strike = df_stock[df_stock[COL_STRIKE] == strike]
            call_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("CE", na=False)]
            put_row = df_strike[df_strike[COL_TRADING_SYM].str.endswith("PE", na=False)]
            
            if call_row.empty or put_row.empty: continue
            
            c_id = int(float(call_row.iloc[0][COL_TOKEN]))
            p_id = int(float(put_row.iloc[0][COL_TOKEN]))
            c_sym = call_row.iloc[0][COL_TRADING_SYM]
            p_sym = put_row.iloc[0][COL_TRADING_SYM]
            
            batch_instruments.append((c_id, c_sym))
            batch_instruments.append((p_id, p_sym))
            strike_pairs[strike] = (c_id, p_id)
            
        if not batch_instruments:
            print(f"❌ {stock}: No CE/PE tokens built for current expiry.")
            return

        # ⚙️ லாக்ஸில் என்ன டோக்கன்கள் அனுப்பப்படுகின்றன என்று பார்க்க பிரிண்ட் செய்கிறோம் (Debug)
        print(f"📡 Requesting Batch Tokens for {stock}: {batch_instruments[:4]}... Total: {len(batch_instruments)}")

        ltp_data_map = get_dhan_batch_ltp(batch_instruments, segment="NSE_FO")
        
        selected_strike = None
        selected_call_ltp = 0.0
        selected_put_ltp = 0.0
        call_put_diff = 0.0
        
        for strike in closest_strikes:
            if strike not in strike_pairs: continue
            c_id, p_id = strike_pairs[strike]
            
            c_ltp = ltp_data_map.get(c_id, 0.0)
            p_ltp = ltp_data_map.get(p_id, 0.0)
            
            if c_ltp == 0.0 or p_ltp == 0.0: continue
            
            diff = abs(c_ltp - p_ltp)
            if diff <= gap_limit:
                selected_strike = strike
                selected_call_ltp = c_ltp
                selected_put_ltp = p_ltp
                call_put_diff = diff
                break
                
        if selected_strike is None:
            min_diff = 999999
            for strike in closest_strikes:
                if strike not in strike_pairs: continue
                c_id, p_id = strike_pairs[strike]
                c_ltp = ltp_data_map.get(c_id, 0.0)
                p_ltp = ltp_data_map.get(p_id, 0.0)
                
                if c_ltp > 0.0 and p_ltp > 0.0:
                    diff = abs(c_ltp - p_ltp)
                    if diff < min_diff:
                        min_diff = diff
                        selected_strike = strike
                        selected_call_ltp = c_ltp
                        selected_put_ltp = p_ltp
                        call_put_diff = diff

        if selected_strike is None:
            # 💡 [INFO LOG] மார்க்கெட் ஆஃப்லைனில் இருந்தால் டோக்கன்கள் 0.0 என்றுதான் வரும், அதை தெளிவாகக் காட்டுகிறோம்.
            print(f"⚠️ {stock}: Active expiry tokens returned 0.0. (If Market is CLOSED, this is NORMAL. Bot will fetch fine during Live Market hours).")
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
                     f"Selected Strike: {int(selected_strike)} | Gap: {gap}\n" \
                     f"Expiry: {current_expiry.strftime('%d-%b-%Y')}\n" \
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
        time.sleep(1)

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    time.sleep(2)
    
    if download_dhan_scrip_master():
        send_telegram("🟢 Multi-Stock Bot Activated (V14.8 - Smart Strike & Debug Mode)!")
        
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
