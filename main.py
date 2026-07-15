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

# வர்த்தகப் பட்டியல் (NIFTY மற்றும் பங்குகள்)
STOCKS_LIST = ["NIFTY", "RELIANCE", "TCS", "INFY", "SBIN", "HDFCBANK", "ICICIBANK", "TATAMOTORS"]

# தற்போதைய தோராயமான சந்தை விலைகள் (Base Strike கண்டறிய)
STOCK_APPROX_PRICES = {
    "NIFTY": 24100,      # நிஃப்டி பேஸ் ஸ்ட்ரைக்
    "RELIANCE": 1300,
    "TCS": 2200,
    "INFY": 1080,
    "SBIN": 1030, 
    "HDFCBANK": 820,
    "ICICIBANK": 1400,
    "TATAMOTORS": 950
}

# ஒவ்வொரு குறியீட்டிற்குமான Strike Gap விபரம்
STRIKE_GAPS = {
    "NIFTY": 50,
    "RELIANCE": 20,
    "TCS": 50,
    "INFY": 20,
    "SBIN": 10,
    "HDFCBANK": 10,
    "ICICIBANK": 15,
    "TATAMOTORS": 10
}

PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

COL_TOKEN = None
COL_INST_NAME = None
COL_UNDERLYING = None
COL_STRIKE = None
COL_OPTION_TYPE = None
COL_CLOSE = None

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
            
            for col in df.columns:
                col_upper = col.upper()
                if "SMART" in col_upper or "TOKEN" in col_upper or col_upper == "SECURITY_ID":
                    COL_TOKEN = col
                elif "INSTRUMENT" in col_upper or col_upper == "INSTRUMENT":
                    COL_INST_NAME = col
                elif "TRADING_SYMBOL" in col_upper or "UNDERLYING" in col_upper:
                    COL_UNDERLYING = col
                elif "STRIKE" in col_upper:
                    COL_STRIKE = col
                elif "OPTION" in col_upper:
                    COL_OPTION_TYPE = col
                elif "CLOSE" in col_upper or "CUSTOM_CLOSE" in col_upper:
                    COL_CLOSE = col
            
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Security ID தேடுதல்
# ------------------------------------------
def get_dhan_option_details(stock_name, target_strike, option_type):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_UNDERLYING, COL_STRIKE, COL_OPTION_TYPE, COL_CLOSE
    if DHAN_MASTER_DF is None:
        return None, 0.0, target_strike
    
    try:
        # NIFTY மற்றும் TATAMOTORS குறியீடுகளைத் துல்லியமாக வடிகட்ட பிரத்யேக லாஜிக்
        if stock_name == "NIFTY":
            df_filter = DHAN_MASTER_DF[
                (DHAN_MASTER_DF[COL_INST_NAME] == 'OPTIDX') & 
                (DHAN_MASTER_DF[COL_UNDERLYING].str.startswith("NIFTY", na=False)) &
                (DHAN_MASTER_DF[COL_OPTION_TYPE] == option_type)
            ].copy()
        elif stock_name == "TATAMOTORS":
            df_filter = DHAN_MASTER_DF[
                (DHAN_MASTER_DF[COL_INST_NAME] == 'OPTSTK') & 
                (DHAN_MASTER_DF[COL_UNDERLYING].str.contains("TATA", na=False)) &
                (DHAN_MASTER_DF[COL_UNDERLYING].str.contains("MOTOR", na=False)) &
                (DHAN_MASTER_DF[COL_OPTION_TYPE] == option_type)
            ].copy()
        else:
            df_filter = DHAN_MASTER_DF[
                (DHAN_MASTER_DF[COL_INST_NAME] == 'OPTSTK') & 
                (DHAN_MASTER_DF[COL_UNDERLYING].str.startswith(stock_name, na=False)) &
                (DHAN_MASTER_DF[COL_OPTION_TYPE] == option_type)
            ].copy()
        
        if df_filter.empty:
            return None, 0.0, target_strike

        df_filter[COL_STRIKE] = pd.to_numeric(df_filter[COL_STRIKE], errors='coerce')
        df_filter['strike_diff'] = (df_filter[COL_STRIKE] - float(target_strike)).abs()
        df_sorted = df_filter.sort_values(by='strike_diff')
        
        if not df_sorted.empty:
            row = df_sorted.iloc[0]
            security_id = row.get(COL_TOKEN)
            security_id = int(float(security_id))
            close_price = float(row.get(COL_CLOSE, 0.0))
            strike_found = float(row.get(COL_STRIKE, target_strike))
            
            return security_id, close_price, strike_found
    except Exception as e:
        print(f"Error finding ID for {stock_name}: {e}")
    return None, 0.0, target_strike

# ------------------------------------------
# 5. Live LTP API Call (Dhan Credentials)
# ------------------------------------------
def get_dhan_live_ltp(security_id, is_index=False):
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
    
    # NIFTY ஆக இருந்தால் NSE_IDX, பங்குகளாக இருந்தால் NSE_FO
    exchange_segment = "NSE_IDX" if is_index else "NSE_FO"
    
    payload = {
        "instruments": [{"exchangeSegment": exchange_segment, "securityId": str(security_id)}]
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
# 6. Pre-Market செட்டப் (Strikes Locking)
# ------------------------------------------
def run_pre_market_logic():
    print("Running Pre-Market Analysis & Base Strike Setup...")
    global PRE_MARKET_SELECTED_STRIKES
    
    for stock in STOCKS_LIST:
        try:
            target_strike = STOCK_APPROX_PRICES.get(stock, 1000)
            call_id, call_ltp_close, call_strike_actual = get_dhan_option_details(stock, target_strike, "CE")
            put_id, put_ltp_close, put_strike_actual = get_dhan_option_details(stock, target_strike, "PE")
            
            if call_id and put_id:
                PRE_MARKET_SELECTED_STRIKES[stock] = {
                    "selected_strike": call_strike_actual,
                    "call_security_id": call_id,
                    "put_security_id": put_id
                }
                print(f"Setup Locked for {stock}: Strike {call_strike_actual}")
            else:
                print(f"Could not find any option contracts for {stock}")
        except Exception as e:
            print(f"Error in Pre-market setup for {stock}: {e}")

# ------------------------------------------
# 7. உங்கள் 7 விதிகள் + சிக்னல் லாஜிக் (Live Monitoring)
# ------------------------------------------
def monitor_live_market():
    print("Checking Live Market with 7-Step Formula...")
    if not PRE_MARKET_SELECTED_STRIKES:
        run_pre_market_logic()
        return

    for stock, setup in PRE_MARKET_SELECTED_STRIKES.items():
        try:
            selected_strike = setup["selected_strike"]
            is_nifty_index = (stock == "NIFTY")
            
            # Dhan API மூலம் நேரலை விலையைப் பெறுதல்
            call_ltp_live = get_dhan_live_ltp(setup["call_security_id"], is_nifty_index)
            put_ltp_live = get_dhan_live_ltp(setup["put_security_id"], is_nifty_index)
            
            # மார்க்கெட் முடிந்த நேரத்தில் கணக்கீடு சரிபார்க்க தோராயமான பேக்அப் டேட்டா (Testing Fallback)
            if call_ltp_live == 0.0:
                call_ltp_live = 88.0 if stock == "NIFTY" else 15.0
            if put_ltp_live == 0.0:
                put_ltp_live = 96.0 if stock == "NIFTY" else 18.0
                
            gap = STRIKE_GAPS.get(stock, 50)
            
            # Rule 1 & 2: Call-Put LTP Difference
            ltp_difference = abs(call_ltp_live - put_ltp_live)
            
            # Rule 3: Calculate Average and round to nearest Strike Gap
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
                alert_msg = f"🟢 **BUY SIGNAL: {stock}** 🟢\n\n" \
                            f"📦 **{stock} {int(call_strike)} CE BUY = {int(trigger_value)}**\n" \
                            f"🎯 **Target 1:** {int(trigger_value + 50)}\n" \
                            f"🎯 **Target 2:** {int(trigger_value + 100)}\n" \
                            f"🎯 **Target 3:** {int(trigger_value + 200)}\n" \
                            f"🛑 **Stop Loss:** {int(put_strike)} PE > {put_diff:.2f}\n\n" \
                            f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
                send_telegram(alert_msg)
                
            # 🔴 2. PE BUY SIGNAL GENERATION
            elif put_ltp_live >= trigger_value and call_ltp_live < call_diff:
                alert_msg = f"🔴 **BUY SIGNAL: {stock}** 🔴\n\n" \
                            f"📦 **{stock} {int(put_strike)} PE BUY = {int(trigger_value)}**\n" \
                            f"🎯 **Target 1:** {int(trigger_value + 50)}\n" \
                            f"🎯 **Target 2:** {int(trigger_value + 100)}\n" \
                            f"🎯 **Target 3:** {int(trigger_value + 200)}\n" \
                            f"🛑 **Stop Loss:** {int(call_strike)} CE > {call_diff:.2f}\n\n" \
                            f"ℹ️ _Live LTP: CE {call_ltp_live} | PE {put_ltp_live}_"
                send_telegram(alert_msg)
                
            # தினசரி கால்குலேஷன் ரிப்போர்ட்டை மட்டும் இப்போதைக்கு டெஸ்ட் செய்ய உடனே டெலிகிராமுக்கு அனுப்புகிறது
            test_report = f"📊 *DHAN LIVE CALCULATOR REPORT: {stock}*\n" \
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
            print(f"Error in Live monitor for {stock}: {e}")

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
        send_telegram("🟢 Dhan API Bot: Connected via GitHub & Live on Render!")
    else:
        send_telegram("🔴 Dhan API Bot: Master Scrip Download Failed!")
        
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    while True:
        now_ist = datetime.now(IST).time()
        market_start = datetime(2000, 1, 1, 9, 15, 0).time()
        market_end = datetime(2000, 1, 1, 15, 30, 0).time()
        
        # லைவ் மார்க்கெட் நேரத்தில் மட்டும் பாட் சிக்னல் தேடும்
        if market_start <= now_ist <= market_end:
            monitor_live_market()
            time.sleep(60)
        else:
            # டெஸ்டிங்கிற்காக மார்க்கெட் இல்லாத நேரத்திலும் ஒரு முறை கால்குலேஷனை ரன் செய்து காட்டுகிறது
            monitor_live_market()
            print(f"Market Closed (IST Time: {now_ist.strftime('%H:%M:%S')}). Waiting...")
            time.sleep(300) # 5 நிமிடத்திற்கு ஒரு முறை ரன் ஆகும்
