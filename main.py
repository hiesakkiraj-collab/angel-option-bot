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

# காலம் மேப்பிங்ஸ் (கண்டிப்பான இயல்புநிலை மதிப்புகள்)
COL_TOKEN = "SEM_SMART_TOKEN"         
COL_INST_NAME = "SEM_INSTRUMENT_NAME"  
COL_UNDERLYING = "SEM_TRADING_SYMBOL"  
COL_STRIKE = "SEM_STRIKE_PRICE"        
COL_OPTION_TYPE = "SEM_OPTION_TYPE"    
COL_CLOSE = "SEM_CUSTOM_CLOSE"         

IST = timezone(timedelta(hours=5, minutes=30))

# ------------------------------------------
# 2. Telegram அலர்ட் ஃபங்க்ஷன்
# ------------------------------------------
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
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_UNDERLYING, COL_STRIKE, COL_OPTION_TYPE, COL_CLOSE
    print("Downloading Dhan Scrip Master File... Please wait...")
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            csv_data = io.StringIO(response.text)
            df = pd.read_csv(csv_data, low_memory=False, encoding='utf-8-sig')
            df.columns = df.columns.str.strip()
            DHAN_MASTER_DF = df
            
            print("Dhan Scrip Master Downloaded Successfully!")
            
            # துல்லியமான காலம் கண்டறிதல் மாடல்
            for col in df.columns:
                col_upper = col.upper()
                if "SMART_TOKEN" in col_upper or "SEM_SMART_TOKEN" in col_upper or col_upper == "SECURITY_ID":
                    COL_TOKEN = col
                elif "INSTRUMENT_NAME" in col_upper or "SEM_INSTRUMENT_NAME" in col_upper:
                    COL_INST_NAME = col
                elif "TRADING_SYMBOL" in col_upper or "SEM_TRADING_SYMBOL" in col_upper:
                    COL_UNDERLYING = col
                elif "STRIKE_PRICE" in col_upper or "SEM_STRIKE_PRICE" in col_upper:
                    COL_STRIKE = col
                elif "OPTION_TYPE" in col_upper or "SEM_OPTION_TYPE" in col_upper:
                    COL_OPTION_TYPE = col
                elif "CUSTOM_CLOSE" in col_upper or "SEM_CUSTOM_CLOSE" in col_upper or "CLOSE" in col_upper:
                    COL_CLOSE = col
            
            print(f"Columns Mapped -> Token: {COL_TOKEN}, Inst: {COL_INST_NAME}, Strike: {COL_STRIKE}")
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Security ID தேடுதல் (Super Safe Mode)
# ------------------------------------------
def get_dhan_option_details(stock_name, target_strike, option_type):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_UNDERLYING, COL_STRIKE, COL_OPTION_TYPE, COL_CLOSE
    if DHAN_MASTER_DF is None:
        return None, 0.0, target_strike
    
    try:
        # காலம் பெயர்கள் இருப்பதை உறுதி செய்தல்
        t_col = COL_TOKEN if COL_TOKEN in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[0]
        i_col = COL_INST_NAME if COL_INST_NAME in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[1]
        u_col = COL_UNDERLYING if COL_UNDERLYING in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[2]
        s_col = COL_STRIKE if COL_STRIKE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[3]
        o_col = COL_OPTION_TYPE if COL_OPTION_TYPE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[4]
        c_col = COL_CLOSE if COL_CLOSE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[5]

        # 1. OPTSTK மற்றும் 'SBIN' குறியீட்டை மட்டும் ஃபில்டர் செய்கிறோம்
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[i_col].isin(['OPTSTK', 'OPTIDX'])) & 
            (DHAN_MASTER_DF[u_col].str.contains(stock_name, case=False, na=False)) &
            (DHAN_MASTER_DF[o_col].str.upper() == option_type.upper())
        ].copy()
        
        if df_filter.empty:
            return None, 0.0, target_strike

        # ⭐️ 2. இங்கேயே 'BSE' போன்ற டெக்ஸ்டுகளைத் தூக்குகிறோம்
        # ஸ்ட்ரைக் காலமை ஸ்ட்ரிங்காக மாற்றி, எண்களைத் தவிர மற்ற டெக்ஸ்ட் இருந்தால் அந்த ரோவை நீக்குகிறது
        df_filter[s_col] = df_filter[s_col].astype(str).str.strip()
        df_filter = df_filter[df_filter[s_col].str.match(r'^\d+(\.\d+)?$', na=False)]
        
        # 3. இப்போது பாதுகாப்பாக numeric-ஆக கன்வெர்ட் செய்கிறோம்
        df_filter[s_col] = pd.to_numeric(df_filter[s_col], errors='coerce')
        df_filter = df_filter.dropna(subset=[t_col, s_col])
        
        if df_filter.empty:
            return None, 0.0, target_strike
            
        # 4. டார்கெட் ஸ்ட்ரைக்கிற்கு அருகில் உள்ளதை எடுத்தல்
        df_filter['strike_diff'] = (df_filter[s_col] - float(target_strike)).abs()
        df_sorted = df_filter.sort_values(by='strike_diff')
        
        if not df_sorted.empty:
            row = df_sorted.iloc[0]
            
            security_id_raw = row.get(t_col)
            if pd.isna(security_id_raw) or security_id_raw is None:
                return None, 0.0, target_strike
                
            security_id = int(float(security_id_raw))
            
            close_raw = row.get(c_col, 0.0)
            close_price = pd.to_numeric(close_raw, errors='coerce')
            close_price = float(close_price) if not pd.isna(close_price) else 0.0
            
            strike_found = float(row.get(s_col, target_strike))
            
            return security_id, close_price, strike_found
            
    except Exception as e:
        print(f"Error finding ID for {stock_name} ({option_type}): {e}")
    return None, 0.0, target_strike

# ------------------------------------------
# 5. Live LTP API Call (Dhan Credentials)
# ------------------------------------------
def get_dhan_live_ltp(security_id):
    if not ACCESS_TOKEN or not CLIENT_ID or not security_id:
        return 0.0
        
    headers = {
        'access-token': ACCESS_TOKEN,
        'client-id': CLIENT_ID,
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {"instruments": [{"exchangeSegment": "NSE_FO", "securityId": str(security_id)}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("data", data.get("Data", {}))
            return float(resp_data.get(str(security_id), {}).get("ltp", 0.0))
    except Exception:
        pass
    return 0.0

# ------------------------------------------
# 6. Pre-Market செட்டப் (SBIN ஸ்ட்ரைக் லாக்கிங்)
# ------------------------------------------
def run_pre_market_logic():
    print("Running Pre-Market Analysis for SBIN...")
    global PRE_MARKET_SELECTED_STRIKES
    
    try:
        target_strike = STOCK_APPROX_PRICES["SBIN"]
        call_id, call_ltp_close, call_strike_actual = get_dhan_option_details("SBIN", target_strike, "CE")
        put_id, put_ltp_close, put_strike_actual = get_dhan_option_details("SBIN", target_strike, "PE")
        
        if call_id and put_id:
            PRE_MARKET_SELECTED_STRIKES["SBIN"] = {
                "selected_strike": call_strike_actual,
                "call_security_id": call_id,
                "put_security_id": put_id
            }
            print(f"✅ Setup Locked for SBIN: Strike {call_strike_actual}")
        else:
            print(f"❌ Could not find SBIN contracts. Call ID: {call_id}, Put ID: {put_id}")
    except Exception as e:
        print(f"Error in Pre-market setup for SBIN: {e}")

# ------------------------------------------
# 7. லைவ் கண்காணிப்பு & 7 படிகள் ஃபார்முலா
# ------------------------------------------
def monitor_live_market():
    print("Checking Live Market with 7-Step Formula for SBIN...")
    if not PRE_MARKET_SELECTED_STRIKES:
        run_pre_market_logic()
        return

    try:
        setup = PRE_MARKET_SELECTED_STRIKES["SBIN"]
        selected_strike = setup["selected_strike"]
        
        call_ltp_live = get_dhan_live_ltp(setup["call_security_id"])
        put_ltp_live = get_dhan_live_ltp(setup["put_security_id"])
        
        # Fallback Simulation values for testing off-market
        if call_ltp_live == 0.0:
            call_ltp_live = 15.0
        if put_ltp_live == 0.0:
            put_ltp_live = 18.0
            
        gap = STRIKE_GAPS["SBIN"]
        
        ltp_difference = abs(call_ltp_live - put_ltp_live)
        avg_ltp = (call_ltp_live + put_ltp_live) / 2
        rounded_value = round(avg_ltp / gap) * gap
        
        call_strike = selected_strike - rounded_value
        put_strike = selected_strike + rounded_value
        
        if put_ltp_live > call_ltp_live:
            adjusted_value = selected_strike - ltp_difference
        else:
            adjusted_value = selected_strike + ltp_difference
            
        call_diff = adjusted_value - call_strike
        put_diff = put_strike - adjusted_value
        
        trigger_value = rounded_value * 2
        
        # CE BUY SIGNAL
        if call_ltp_live >= trigger_value and put_ltp_live < put_diff:
            alert_msg = f"🟢 **BUY SIGNAL: SBIN** 🟢\n\n" \
                        f"📦 **SBIN {int(call_strike)} CE BUY = {int(trigger_value)}**\n" \
                        f"🎯 **Target 1:** {int(trigger_value + 10)}\n" \
                        f"🎯 **Target 2:** {int(trigger_value + 20)}\n" \
                        f"🛑 **Stop Loss:** {int(put_strike)} PE > {put_diff:.2f}\n\n" \
                        f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
            send_telegram(alert_msg)
            
        # PE BUY SIGNAL
        elif put_ltp_live >= trigger_value and call_ltp_live < call_diff:
            alert_msg = f"🔴 **BUY SIGNAL: SBIN** 🔴\n\n" \
                        f"📦 **SBIN {int(put_strike)} PE BUY = {int(trigger_value)}**\n" \
                        f"🎯 **Target 1:** {int(trigger_value + 10)}\n" \
                        f"🎯 **Target 2:** {int(trigger_value + 20)}\n" \
                        f"🛑 **Stop Loss:** {int(call_strike)} CE > {call_diff:.2f}\n\n" \
                        f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
            send_telegram(alert_msg)
            
        test_report = f"📊 *DHAN LIVE CALCULATOR REPORT: SBIN*\n" \
                      f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n" \
                      f"🎯 *Selected Strike:* {selected_strike}\n" \
                      f"📞 *Call LTP:* {call_ltp_live}  |  📈 *Put LTP:* {put_ltp_live}\n" \
                      f"↔️ *LTP Difference:* {ltp_difference:.2f}\n" \
                      f"🔄 *Rounded Value:* {rounded_value}  |  ⚡ *Trigger (RV*2):* {trigger_value}\n" \
                      f"🔵 *Call Strike:* {int(call_strike)}  |  🔴 *Put Strike:* {int(put_strike)}\n" \
                      f"⚖️ *Adjusted Value:* {adjusted_value:.2f}\n" \
                      f"🔹 *Call Difference:* {call_diff:.2f}\n" \
                      f"🔸 *Put Difference:* {put_diff:.2f}\n" \
                      f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n" \
                      f"📢 *Target Signals:*\n" \
                      f"👉 *CE BUY:* {int(call_strike)} CE at {int(trigger_value)} (SL if PE > {put_diff:.2f})\n" \
                      f"👉 *PE BUY:* {int(put_strike)} PE at {int(trigger_value)} (SL if CE > {call_diff:.2f})"
        
        send_telegram(test_report)
        
    except Exception as e:
        print(f"Error in Live monitor for SBIN: {e}")

# ------------------------------------------
# 8. Web Server (Keep-Alive)
# ------------------------------------------
def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    handler = SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    
    print(f"Starting server on port {port} for Render keep-alive...")
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error on port {port}: {e}")

# ------------------------------------------
# 9. Main Execution
# ------------------------------------------
if __name__ == "__main__":
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    time.sleep(5)
    
    download_success = download_dhan_scrip_master()
    if download_success:
        run_pre_market_logic()
        send_telegram("🟢 SBIN Option Bot: Connected & Live on Render!")
    else:
        send_telegram("🔴 Dhan API Bot: Master Scrip Download Failed!")
    
    while True:
        now_ist = datetime.now(IST).time()
        market_start = datetime(2000, 1, 1, 9, 15, 0).time()
        market_end = datetime(2000, 1, 1, 15, 30, 0).time()
        
        if market_start <= now_ist <= market_end:
            monitor_live_market()
            time.sleep(60)
        else:
            monitor_live_market()
            print(f"Market Closed (IST Time: {now_ist.strftime('%H:%M:%S')}). Waiting...")
            time.sleep(300)
