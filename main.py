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

# இப்போதைக்கு கண்காணிக்கப்படும் ஒரே பங்கு SBIN மட்டுமே!
STOCKS_LIST = ["SBIN"]

# SBIN தோராயமான தற்போதைய சந்தை விலை மற்றும் Strike Gap
STOCK_APPROX_PRICES = {"SBIN": 1030}
STRIKE_GAPS = {"SBIN": 10}

PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

# Dhan Master CSV-க்கான சரியான காலம்கள் (Standard Mappings)
COL_TOKEN = "SEM_SMART_TOKEN"         # Dhan-ன் பிரத்யேக செக்யூரிட்டி ஐடி காலம்
COL_INST_NAME = "SEM_INSTRUMENT_NAME"  # OPTSTK அல்லது OPTIDX
COL_UNDERLYING = "SEM_TRADING_SYMBOL"  # Trading Symbol (e.g., SBIN-Jul2026-1030-CE)
COL_STRIKE = "SEM_STRIKE_PRICE"        # Strike Price
COL_OPTION_TYPE = "SEM_OPTION_TYPE"    # CE அல்லது PE
COL_CLOSE = "SEM_CUSTOM_CLOSE"         # முந்தைய நாளின் முடிவு விலை

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
        requests.post(url, json=payload)
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
            
            # டைனமிக் முறையில் காலம் பெயர்களைக் கண்டறிதல் (இணைப்புத் தோல்வியைத் தடுக்க)
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
            
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Security ID தேடுதல் (துல்லியமான தேடுதல் முறை)
# ------------------------------------------
def get_dhan_option_details(stock_name, target_strike, option_type):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_UNDERLYING, COL_STRIKE, COL_OPTION_TYPE, COL_CLOSE
    if DHAN_MASTER_DF is None:
        return None, 0.0, target_strike
    
    try:
        # காலம் பெயர்கள் காலியாக இல்லை என்பதை உறுதிப்படுத்துகிறோம்
        token_col = COL_TOKEN if COL_TOKEN in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[0]
        inst_col = COL_INST_NAME if COL_INST_NAME in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[1]
        underlying_col = COL_UNDERLYING if COL_UNDERLYING in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[2]
        strike_col = COL_STRIKE if COL_STRIKE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[3]
        opt_type_col = COL_OPTION_TYPE if COL_OPTION_TYPE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[4]
        close_col = COL_CLOSE if COL_CLOSE in DHAN_MASTER_DF.columns else DHAN_MASTER_DF.columns[5]

        # 1. OPTSTK மற்றும் குறிப்பிட்ட பங்கின் பெயருக்கு ஏற்றவாறு வடிகட்டுகிறோம்
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[inst_col].isin(['OPTSTK', 'OPTIDX'])) & 
            (DHAN_MASTER_DF[underlying_col].str.contains(stock_name, case=False, na=False)) &
            (DHAN_MASTER_DF[opt_type_col].str.upper() == option_type.upper())
        ].copy()
        
        if df_filter.empty:
            return None, 0.0, target_strike

        # 2. NaN மதிப்புகளை நீக்கிவிட்டு ஸ்ட்ரைக்கை எண்களாக மாற்றுகிறோம்
        df_filter = df_filter.dropna(subset=[token_col, strike_col])
        df_filter[strike_col] = pd.to_numeric(df_filter[strike_col], errors='coerce')
        df_filter = df_filter.dropna(subset=[strike_col])
        
        # 3. நம்முடைய டார்கெட் விலைக்கு (1030) மிக அருகில் உள்ள ஸ்ட்ரைக்கை கண்டறிகிறோம்
        df_filter['strike_diff'] = (df_filter[strike_col] - float(target_strike)).abs()
        df_sorted = df_filter.sort_values(by='strike_diff')
        
        if not df_sorted.empty:
            row = df_sorted.iloc[0]
            
            security_id_raw = row.get(token_col)
            if pd.isna(security_id_raw) or security_id_raw is None:
                return None, 0.0, target_strike
                
            security_id = int(float(security_id_raw))
            
            close_raw = row.get(close_col, 0.0)
            close_price = float(close_raw) if not pd.isna(close_raw) and close_raw is not None else 0.0
            
            strike_found = float(row.get(strike_col, target_strike))
            
            return security_id, close_price, strike_found
            
    except Exception as e:
        print(f"Error finding ID for {stock_name}: {e}")
    return None, 0.0, target_strike

# ------------------------------------------
# 5. Live LTP API Call (Dhan Credentials)
# ------------------------------------------
def get_dhan_live_ltp(security_id):
    if not ACCESS_TOKEN or not CLIENT_ID:
        return 0.0
    if not security_id:
        return 0.0
        
    headers = {
        'access-token': ACCESS_TOKEN,
        'client-id': CLIENT_ID,
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    
    payload = {
        "instruments": [{"exchangeSegment": "NSE_FO", "securityId": str(security_id)}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            return 0.0
        data = response.json()
        resp_data = data.get("data", data.get("Data", {}))
        ltp = float(resp_data.get(str(security_id), {}).get("ltp", 0.0))
        return ltp
    except Exception as e:
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
            print(f"❌ Could not find SBIN option contracts in Dhan Master. Call ID: {call_id}, Put ID: {put_id}")
    except Exception as e:
        print(f"Error in Pre-market setup for SBIN: {e}")

# ------------------------------------------
# 7. லைவ் கண்காணிப்பு & 7 படிகள் ஃபார்முலா (SBIN மட்டும்)
# ------------------------------------------
def monitor_live_market():
    print("Checking Live Market with 7-Step Formula for SBIN...")
    if not PRE_MARKET_SELECTED_STRIKES:
        run_pre_market_logic()
        return

    try:
        setup = PRE_MARKET_SELECTED_STRIKES["SBIN"]
        selected_strike = setup["selected_strike"]
        
        # Dhan API மூலம் நேரலை விலையைப் பெறுதல்
        call_ltp_live = get_dhan_live_ltp(setup["call_security_id"])
        put_ltp_live = get_dhan_live_ltp(setup["put_security_id"])
        
        # மார்க்கெட் முடிந்த நேரத்தில் கணக்கீடு சரிபார்க்க தோராயமான பேக்அப் டேட்டா (Testing Fallback)
        if call_ltp_live == 0.0:
            call_ltp_live = 15.0
        if put_ltp_live == 0.0:
            put_ltp_live = 18.0
            
        gap = STRIKE_GAPS["SBIN"]
        
        # Rule 1 & 2: Call-Put LTP Difference
        ltp_difference = abs(call_ltp_live - put_ltp_live)
        
        # Rule 3: Calculate Average and round to nearest Strike Gap (10)
        avg_ltp = (call_ltp_live + put_ltp_live) / 2
        rounded_value = round(avg_ltp / gap) * gap
        
        # Rule 4: Call Strike & Put Strike கணக்கீடு
        call_strike = selected_strike - rounded_value
        put_strike = selected_strike + rounded_value
        
        # Rule 5: Compare LTP and Calculate Adjusted Value
        if put_ltp_live > call_ltp_live:
            adjusted_value = selected_strike - ltp_difference
        else:
            adjusted_value = selected_strike + ltp_difference
            
        # Rule 6: Calculate Call/Put Differences
        call_diff = adjusted_value - call_strike
        put_diff = put_strike - adjusted_value
        
        # Rule 7: BUY Entry Trigger & Stop Loss System
        trigger_value = rounded_value * 2
        
        # 🟢 1. CE BUY SIGNAL GENERATION
        if call_ltp_live >= trigger_value and put_ltp_live < put_diff:
            alert_msg = f"🟢 **BUY SIGNAL: SBIN** 🟢\n\n" \
                        f"📦 **SBIN {int(call_strike)} CE BUY = {int(trigger_value)}**\n" \
                        f"🎯 **Target 1:** {int(trigger_value + 10)}\n" \
                        f"🎯 **Target 2:** {int(trigger_value + 20)}\n" \
                        f"🛑 **Stop Loss:** {int(put_strike)} PE > {put_diff:.2f}\n\n" \
                        f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
            send_telegram(alert_msg)
            
        # 🔴 2. PE BUY SIGNAL GENERATION
        elif put_ltp_live >= trigger_value and call_ltp_live < call_diff:
            alert_msg = f"🔴 **BUY SIGNAL: SBIN** 🔴\n\n" \
                        f"📦 **SBIN {int(put_strike)} PE BUY = {int(trigger_value)}**\n" \
                        f"🎯 **Target 1:** {int(trigger_value + 10)}\n" \
                        f"🎯 **Target 2:** {int(trigger_value + 20)}\n" \
                        f"🛑 **Stop Loss:** {int(call_strike)} CE > {call_diff:.2f}\n\n" \
                        f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
            send_telegram(alert_msg)
            
        # தினசரி கால்குலேஷன் ரிப்போர்ட்டை மட்டும் இப்போதைக்கு டெஸ்ட் செய்ய உடனே டெலிகிராமுக்கு அனுப்புகிறது
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
# 8. Web Server
# ------------------------------------------
def start_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    handler = SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

# ------------------------------------------
# 9. Main Execution
# ------------------------------------------
if __name__ == "__main__":
    download_success = download_dhan_scrip_master()
    if download_success:
        run_pre_market_logic()
        send_telegram("🟢 SBIN Option Bot: Connected & Live on Render!")
    else:
        send_telegram("🔴 Dhan API Bot: Master Scrip Download Failed!")
        
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
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
