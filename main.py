import os
import time
import requests
import pandas as pd
import io
from datetime import datetime
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

# 210 ஸ்டாக்குகளின் பட்டியல் (உதாரணத்திற்கு 7 ஸ்டாக்குகள்)
STOCKS_LIST = ["RELIANCE", "TCS", "INFY", "SBIN", "HDFCBANK", "ICICIBANK", "TATAMOTORS"]
STRIKE_GAP = 50  

# குளோபல் மெமரி மற்றும் மாஸ்டர் டேட்டாபிரேம்
PRE_MARKET_SELECTED_STRIKES = {}
DHAN_MASTER_DF = None

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
# 3. Dhan Master Scrip டவுன்லோடு செய்யும் ஃபங்க்ஷன்
# ------------------------------------------
def download_dhan_scrip_master():
    global DHAN_MASTER_DF
    print("Downloading Dhan Scrip Master File... Please wait...")
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # CSV டேட்டாவை மெமரியில் படித்து பான்டாஸ் டேட்டாபிரேமாக மாற்றுதல்
            csv_data = io.StringIO(response.text)
            DHAN_MASTER_DF = pd.read_csv(csv_data)
            # ஸ்பேஸ் எரர் வராமல் இருக்க காலம்களின் பெயர்களை ட்ரிம் செய்தல்
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
# 4. குறிப்பிட்ட ஆப்ஷனின் Security ID மற்றும் Close LTP தேடும் ஃபங்க்ஷன்
# ------------------------------------------
def get_dhan_option_details(stock_name, strike_price, option_type):
    global DHAN_MASTER_DF
    if DHAN_MASTER_DF is None:
        return None, 0.0
    
    try:
        # தனுக்கான மாஸ்டர் ஃபைலில் ஆப்ஷன் காண்ட்ராக்ட்களை ஃபில்டர் செய்தல்
        # OptionType: 'CE' அல்லது 'PE', SEM_EXPIRY_FLAG: 'CURRENT' (நடைமுறை எக்ஸ்பைரி)
        df_filter = DHAN_MASTER_DF[
            (DHAN_MASTER_DF['SEM_INSTRUMENT_NAME'] == 'OPTSTK') & 
            (DHAN_MASTER_DF['SEM_TRADING_SYMBOL'].str.startswith(stock_name)) &
            (DHAN_MASTER_DF['SEM_STRIKE_PRICE'] == float(strike_price)) &
            (DHAN_MASTER_DF['SEM_OPTION_TYPE'] == option_type)
        ]
        
        if not df_filter.empty:
            # லேட்டஸ்ட் எக்ஸ்பைரி காண்ட்ராக்ட்டை எடுத்தல்
            row = df_filter.iloc[0]
            security_id = int(row['SEM_SMART_TOKEN'])
            close_price = float(row.get('SEM_CUSTOM_CLOSE', 0.0)) # நேற்றைய குளோசிங் விலை
            return security_id, close_price
    except Exception as e:
        print(f"Error finding ID for {stock_name} {strike_price} {option_type}: {e}")
    
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
# 6. Phase 1: பிரீ-மார்க்கெட் க்ளோசிங் டேட்டா கணக்கீடு
# ------------------------------------------
def run_pre_market_logic():
    print("Running Pre-Market Analysis...")
    global PRE_MARKET_SELECTED_STRIKES
    
    # டம்மி விலைகளுக்குப் பதிலாக நிஜமான மாஸ்டர் டேட்டாவில் தேடுகிறோம்
    # உதாரணத்திற்கு SBIN-ல் ஒரு குறிப்பிட்ட ஸ்ட்ரைக் (எ.கா: 6800)
    for stock in STOCKS_LIST:
        try:
            strike_to_check = 7000  # தற்போதைய மார்க்கெட் விலைக்கு அருகிலுள்ள ஒரு ஸ்ட்ரைக்
            
            # Dhan மாஸ்டர் ஃபைலில் இருந்து நேற்றைய குளோசிங் விலையை எடுத்தல்
            call_id, call_ltp_close = get_dhan_option_details(stock, strike_to_check, "CE")
            put_id, put_ltp_close = get_dhan_option_details(stock, strike_to_check, "PE")
            
            if call_id and put_id:
                diff = abs(call_ltp_close - put_ltp_close)
                if diff <= (STRIKE_GAP / 2):
                    PRE_MARKET_SELECTED_STRIKES[stock] = {
                        "selected_strike": strike_to_check,
                        "call_security_id": call_id,
                        "put_security_id": put_id
                    }
                    print(f"Setup Locked for {stock}: Strike {strike_to_check}")
        except Exception as e:
            print(f"Error in Pre-market setup for {stock}: {e}")

# ------------------------------------------
# 7. Phase 2: லைவ் மார்க்கெட் கண்காணிப்பு
# ------------------------------------------
def monitor_live_market():
    print("Live Market Monitoring...")
    for stock, setup in PRE_MARKET_SELECTED_STRIKES.items():
        try:
            selected_strike = setup["selected_strike"]
            
            # நிஜமான Dhan Live LTP-ஐ ஏபிஐ மூலம் இழுத்தல்
            call_ltp_live = get_dhan_live_ltp(setup["call_security_id"])
            put_ltp_live = get_dhan_live_ltp(setup["put_security_id"])
            
            if call_ltp_live == 0.0 or put_ltp_live == 0.0:
                continue # விலை கிடைக்கவில்லை எனில் தவிர்க்கவும்
                
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
    # 1. மாஸ்டர் ஃபைலை டவுன்லோட் செய்தல்
    download_success = download_dhan_scrip_master()
    
    if download_success:
        send_telegram("🟢 Dhan Smart Bot: Master Scrip Downloaded. Analysis Running...")
        run_pre_market_logic()
    else:
        send_telegram("🔴 Dhan Smart Bot: Master Scrip Download Failed!")
        
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    while True:
        now = datetime.now().time()
        if now >= datetime.strptime("09:15:00", "%H:%M:%S").time() and now <= datetime.strptime("15:30:00", "%H:%M:%S").time():
            monitor_live_market()
            time.sleep(60)
        else:
            print("Market Closed...")
            time.sleep(300)
