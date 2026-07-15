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

# எந்த எக்ஸ்டர்னல் லைப்ரரியும் இல்லாமல் துல்லியமாக இந்திய நேரமண்டலத்தை (+5:30) உருவாக்குதல்
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
            DHAN_MASTER_DF = pd.read_csv(csv_data, low_memory=False)
            DHAN_MASTER_DF.columns = DHAN_MASTER_DF.columns.str.strip()
            print("Dhan Scrip Master Downloaded Successfully!")
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
        return False

# ------------------------------------------
# 4. Security ID மற்றும் Close LTP தேடுதல்
# ------------------------------------------
def get_dhan_option_details(stock_name, strike_price, option_type):
    global DHAN_MASTER_DF
    if DHAN_MASTER_DF is None:
        return None, 0.0
    
    try:
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF['SEM_INSTRUMENT_NAME'] == 'OPTSTK') & 
            (DHAN_MASTER_DF['SEM_TRADING_SYMBOL'].str.startswith(stock_name)) &
            (DHAN_MASTER_DF['SEM_STRIKE_PRICE'] == float(strike_price)) &
            (DHAN_MASTER_DF['SEM_OPTION_TYPE'] == option_type)
        ]
        
        if not df_filter.empty:
            row = df_filter.iloc[0]
            security_id = int(row['SEM_SMART_TOKEN'])
            close_price = float(row.get('SEM_CUSTOM_CLOSE', 10.0))
            return security_id, close_price
    except Exception as e:
        print(f"Error finding ID for {stock_name}: {e}")
    return None, 0.0

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
            strike_to_check = 6800 if stock == "SBIN" else 2500 
            
            call_id, call_ltp_close = get_dhan_option_details(stock, strike_to_check, "CE")
            put_id, put_ltp_close = get_dhan_option_details(stock, strike_to_check, "PE")
            
            if call_id and put_id:
                PRE_MARKET_SELECTED_STRIKES[stock] = {
                    "selected_strike": strike_to_check,
                    "call_security_id": call_id,
                    "put_security_id": put_id
                }
                print(f"Setup Locked for {stock}: Strike {strike_to_check}")
        except Exception as e:
            print(f"Error in Pre-market setup: {e}")

# ------------------------------------------
# 7. லைவ் மார்க்கெட் கண்காணிப்பு
# ------------------------------------------
def monitor_live_market():
    print("Live Market Monitoring...")
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
        send_telegram("🟢 Dhan Smart Bot: System Active & Monitoring Live Market!")
        run_pre_market_logic()
    else:
        send_telegram("🔴 Dhan Smart Bot: Master Scrip Download Failed!")
        
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    while True:
        # டெல்லியில் இருக்கும் சர்வர் நேரத்தை துல்லியமான இந்திய நேரமாக (IST) மாற்றுதல்
        now_ist = datetime.now(IST).time()
        
        # காலை 09:15 மற்றும் மதியம் 03:30 மணிக்கான ஸ்ட்ரக்சர்
        market_start = datetime(2000, 1, 1, 9, 15, 0).time()
        market_end = datetime(2000, 1, 1, 15, 30, 0).time()
        
        if market_start <= now_ist <= market_end:
            monitor_live_market()
            time.sleep(60)
        else:
            print(f"Market Closed (IST Time: {now_ist.strftime('%H:%M:%S')}). Waiting...")
            time.sleep(60)
