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

# ஒவ்வொரு பங்குக்கும் தற்போதைய தோராயமான மார்க்கெட் விலை (உரிய ஸ்ட்ரைக்குகளைக் கண்டறிய)
STOCK_APPROX_PRICES = {
    "RELIANCE": 2500,
    "TCS": 4100,
    "INFY": 1600,
    "SBIN": 840,
    "HDFCBANK": 1700,
    "ICICIBANK": 1150,
    "TATAMOTORS": 950
}

PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

# காலம் பெயர்களுக்கான வேரியபிள்கள்
COL_TOKEN = None
COL_INST_NAME = None
COL_UNDERLYING = None
COL_STRIKE = None
COL_OPTION_TYPE = None
COL_CLOSE = None

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
# 3. Dhan Master Scrip டவுன்லோடு & காலம் பெயர்களைத் தானாகப் பொருத்துதல்
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
            
            # 🔍 காலம் பெயர்களைத் தானாகத் தேர்ந்தெடுத்தல் (Failsafe Substring Matching)
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
            
            # Fallback values
            if not COL_TOKEN and len(df.columns) > 2:
                COL_TOKEN = df.columns[2]
            
            COL_TOKEN = COL_TOKEN or "SEM_SMART_TOKEN"
            COL_INST_NAME = COL_INST_NAME or "SEM_INSTRUMENT_NAME"
            COL_UNDERLYING = COL_UNDERLYING or "SEM_TRADING_SYMBOL"
            COL_STRIKE = COL_STRIKE or "SEM_STRIKE_PRICE"
            COL_OPTION_TYPE = COL_OPTION_TYPE or "SEM_OPTION_TYPE"
            COL_CLOSE = COL_CLOSE or "SEM_CUSTOM_CLOSE"
            
            return True
        else:
            print("Failed to download Scrip Master from Dhan.")
            return False
    except Exception as e:
        print(f"Error downloading Scrip Master: {e}")
    return False

# ------------------------------------------
# 4. Security ID மற்றும் Close LTP தேடுதல் (Failsafe Matching)
# ------------------------------------------
def get_dhan_option_details(stock_name, target_strike, option_type):
    global DHAN_MASTER_DF, COL_TOKEN, COL_INST_NAME, COL_UNDERLYING, COL_STRIKE, COL_OPTION_TYPE, COL_CLOSE
    if DHAN_MASTER_DF is None:
        return None, 0.0, target_strike
    
    try:
        # OPTSTK மற்றும் ஸ்டாக் பெயருடன் தொடங்குவதை ஃபில்டர் செய்கிறது
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF[COL_INST_NAME] == 'OPTSTK') & 
            (DHAN_MASTER_DF[COL_UNDERLYING].str.startswith(stock_name, na=False)) &
            (DHAN_MASTER_DF[COL_OPTION_TYPE] == option_type)
        ].copy()
        
        if df_filter.empty:
            return None, 0.0, target_strike

        df_filter[COL_STRIKE] = pd.to_numeric(df_filter[COL_STRIKE], errors='coerce')
        
        # டார்கெட் ஸ்ட்ரைக்கிற்கு மிக அருகிலுள்ள உண்மையான ஸ்ட்ரைக் விலையைக் கண்டறிதல்
        df_filter['strike_diff'] = (df_filter[COL_STRIKE] - float(target_strike)).abs()
        df_sorted = df_filter.sort_values(by='strike_diff')
        
        if not df_sorted.empty:
            row = df_sorted.iloc[0]
            
            security_id = row.get(COL_TOKEN)
            if pd.isna(security_id):
                security_id = row.iloc[2] if len(row) > 2 else row.iloc[0]
                
            security_id = int(float(security_id))
            close_price = float(row.get(COL_CLOSE, 0.0))
            strike_found = float(row.get(COL_STRIKE, target_strike))
            
            return security_id, close_price, strike_found
    except Exception as e:
        print(f"Error finding ID for {stock_name}: {e}")
    return None, 0.0, target_strike

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
            # தோராயமான விலையைப் பெற்று அதற்கு அருகிலுள்ள உண்மையான ஸ்ட்ரைக்கை தேடும்
            target_strike = STOCK_APPROX_PRICES.get(stock, 1000)
            
            call_id, call_ltp_close, call_strike_actual = get_dhan_option_details(stock, target_strike, "CE")
            put_id, put_ltp_close, put_strike_actual = get_dhan_option_details(stock, target_strike, "PE")
            
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
            
            # API வேலை செய்யவில்லை எனில் காட்டும் தகவல்
            if call_ltp_live == 0.0 or put_ltp_live == 0.0:
                alert_msg = f"⚠️ *LIVE DHAN OPTION SIGNAL: {stock}* ⚠️\n\n" \
                            f"🎯 Base Strike: {selected_strike}\n" \
                            f"❌ *LTP Data N/A* \n" \
                            f"💡 _தயவுசெய்து உங்களின் Dhan Access Token சரியாக உள்ளதா எனச் சரிபார்க்கவும்._"
                send_telegram(alert_msg)
                continue
                
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
        send_telegram("🟢 Dhan Smart Bot: System Ready with Smart Auto-Strike!")
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
