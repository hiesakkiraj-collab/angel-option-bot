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

STOCKS_LIST = ["RELIANCE", "TCS", "INFY", "SBIN", "HDFCBANK", "ICICIBANK", "TATAMOTORS"]
STRIKE_GAP = 50  

PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

# இந்திய நேரமண்டலம் (+5:30)
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
    global DHAN_MASTER_DF
    print("Downloading Dhan Scrip Master File... Please wait...")
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            csv_data = io.StringIO(response.text)
            # UTF-8-sig மூலம் பைட் ஆர்டர் மார்க்கை நீக்கி லோடு செய்தல்
            df = pd.read_csv(csv_data, low_memory=False, encoding='utf-8-sig')
            
            # காலம் பெயர்களை சுத்தப்படுத்துதல்
            df.columns = df.columns.str.strip().str.replace(r'[^\w\s_]', '', regex=True)
            DHAN_MASTER_DF = df
            
            print("Dhan Scrip Master Downloaded Successfully!")
            # 🔍 லாக்ஸில் காலம் பெயர்களை அச்சிட்டுச் சரிபார்க்கிறோம்
            print("--- Actual Columns Found in CSV ---")
            print(list(DHAN_MASTER_DF.columns)[:15])
            print("-----------------------------------")
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Security ID மற்றும் Close LTP தேடுதல் (Failsafe System)
# ------------------------------------------
def get_dhan_option_details(stock_name, strike_price, option_type):
    global DHAN_MASTER_DF
    if DHAN_MASTER_DF is None:
        return None, 0.0, strike_price
    
    try:
        # 'OPTSTK' மற்றும் ஸ்டாக் பெயரை வைத்து ஃபில்டர் செய்தல்
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF['SEM_INSTRUMENT_NAME'] == 'OPTSTK') & 
            (DHAN_MASTER_DF['SEM_TRADING_SYMBOL'].str.startswith(stock_name, na=False)) &
            (DHAN_MASTER_DF['SEM_OPTION_TYPE'] == option_type)
        ]
        
        # குறிப்பிட்ட ஸ்ட்ரைக் விலை உள்ளதா எனப் பார்த்தல்
        df_strike = df_filter[df_filter['SEM_STRIKE_PRICE'] == float(strike_price)]
        if not df_strike.empty:
            df_filter = df_strike
            
        if not df_filter.empty:
            row = df_filter.iloc[0]
            
            # 'SEM_SMART_TOKEN' காலம் பெயர் இருக்கிறதா என்று பார்த்து எடுக்கும், 
            # இல்லையென்றால் முதல் காலத்தில் இருக்கும் மதிப்பை டோக்கனாக எடுத்துக்கொள்ளும்.
            if 'SEM_SMART_TOKEN' in DHAN_MASTER_DF.columns:
                security_id = int(row['SEM_SMART_TOKEN'])
            else:
                security_id = int(row.iloc[0]) # Fallback to first column index
                
            close_price = float(row.get('SEM_CUSTOM_CLOSE', 10.0))
            strike_found = float(row.get('SEM_STRIKE_PRICE', strike_price))
            
            return security_id, close_price, strike_found
    except Exception as e:
        print(f"Error finding ID for {stock_name}: {e}")
    return None, 0.0, strike_price

# ------------------------------------------
# 5. Dhan Live LTP API Call
# ------------------------------------------
def get_dhan_live_ltp(security_id):
    if not ACCESS_TOKEN or not security_id:
        return 0.0
    headers = {
        'access-token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {
        "instruments": [{"exchangeSegment": "NSE_FO", "securityId": str(security_id)}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            return float(data.get("data", {}).get(str(security_id), {}).get("ltp", 0.0))
    except Exception as e:
        print(f"LTP Error for ID {security_id}: {e}")
    return 0.0

# ------------------------------------------
# 6. Pre-Market க்ளோசிங் டேட்டா கணக்கீடு
# ------------------------------------------
def run_pre_market_logic():
    print("Running Pre-Market Analysis...")
    global PRE_MARKET_SELECTED_STRIKES
    
    for stock in STOCKS_LIST:
        try:
            if stock == "SBIN":
                strike_to_check = 850 
            elif stock == "RELIANCE":
                strike_to_check = 2500
            elif stock == "TCS":
                strike_to_check = 4000
            else:
                strike_to_check = 1500
            
            call_id, call_ltp_close, call_strike_actual = get_dhan_option_details(stock, strike_to_check, "CE")
            put_id, put_ltp_close, put_strike_actual = get_dhan_option_details(stock, strike_to_check, "PE")
            
            if call_id and put_id:
                PRE_MARKET_SELECTED_STRIKES[stock] = {
                    "selected_strike": call_strike_actual,
                    "call_security_id": call_id,
                    "put_security_id": put_id
                }
                print(f"Setup Locked for {stock}: Strike {call_strike_actual} (ID: {call_id})")
            else:
                print(f"Could not find any option contracts for {stock}")
        except Exception as e:
            print(f"Error in Pre-market setup for {stock}: {e}")

# ------------------------------------------
# 7. லைவ் மார்க்கெட் கண்காணிப்பு
# ------------------------------------------
def monitor_live_market():
    print("Live Market Monitoring...")
    if not PRE_MARKET_SELECTED_STRIKES:
        print("No stocks configured in Pre-Market Setup! Retrying setup...")
        run_pre_market_logic()
        return

    for stock, setup in PRE_MARKET_SELECTED_STRIKES.items():
        try:
            selected_strike = setup["selected_strike"]
            
            call_ltp_live = get_dhan_live_ltp(setup["call_security_id"])
            put_ltp_live = get_dhan_live_ltp(setup["put_security_id"])
            
            if call_ltp_live == 0.0 or put_ltp_live == 0.0:
                call_ltp_live, put_ltp_live = 85.0, 75.0 
                
            avg_ltp = (call_ltp_live + put_ltp_live) / 2
            rounded_value = round(avg_ltp / STRIKE_GAP) * STRIKE_GAP
            
            call_strike = selected_strike - rounded_value
            put_strike = selected_strike + rounded_value
            
            live_diff = abs(call_ltp_live - put_ltp_live)
            if put_ltp_live > call_ltp_live:
                adjusted_value = selected_strike - live_diff
            else:
                adjusted_value = selected_strike + live_diff
                
            call_diff = adjusted_value - call_strike
            put_diff = put_strike - adjusted_value
            
            alert_msg = f"🚨 *LIVE DHAN OPTION SIGNAL: {stock}* 🚨\n\n" \
                        f"🎯 Base Strike: {selected_strike}\n" \
                        f"📞 Call LTP: {call_ltp_live} | 📈 Put LTP: {put_ltp_live}\n" \
                        f"📞 Call Strike: {call_strike} | 📈 Put Strike: {put_strike}\n" \
                        f"⚖️ Adjusted Value: {adjusted_value:.2f}\n" \
                        f"🔹 Call Diff: {call_diff:.2f} | 🔸 Put Diff: {put_diff:.2f}"
            
            send_telegram(alert_msg)
            
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
        send_telegram("🟢 Dhan Smart Bot: Debug Column Monitoring System Active!")
    else:
        send_telegram("🔴 Dhan Smart Bot: Master Scrip Download Failed!")
        
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
            print(f"Market Closed (IST Time: {now_ist.strftime('%H:%M:%S')}). Waiting...")
            time.sleep(60)
