import os
import time
import requests
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading

# ==========================================
# 1. ரகசிய விபரங்கள் (Render Environment Variables-ல் இருந்து எடுக்கப்படும்)
# ==========================================
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 210 ஸ்டாக்குகளின் பட்டியல்
STOCKS_LIST = ["RELIANCE", "TCS", "INFY", "SBIN", "HDFCBANK", "ICICIBANK", "TATAMOTORS"]
STRIKE_GAP = 50  # ஸ்டாக்கிற்கு ஏத்த மாதிரி மாற்றிக்கொள்ளலாம்

# குளோபல் மெமரி (நேற்றைய முடிவில் தேர்வு செய்யப்பட்ட ஸ்ட்ரைக்குகளை சேமிக்க)
PRE_MARKET_SELECTED_STRIKES = {}

# ------------------------------------------
# 2. Telegram அலர்ட் ஃபங்க்ஷன்
# ------------------------------------------
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram Failed: {response.text}")
    except Exception as e:
        print(f"Telegram Error: {e}")

# ------------------------------------------
# 3. Dhan API மூலம் LTP பெரும் ஃபங்க்ஷன்
# ------------------------------------------
# Dhan-ல் லைவ் அல்லது க்ளோசிங் LTP-ஐப் பெற இந்த ஃபங்க்ஷனைப் பயன்படுத்தலாம்
def get_dhan_ltp(security_id, exchange_segment="NSE_EQ"):
    if not ACCESS_TOKEN:
        return 0.0
    
    headers = {
        'access-token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }
    # Dhan-ன் Security ID-ஐ அடிப்படையாகக் கொண்டு LTP பெறும் ஏபிஐ கால்
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    payload = {
        "instruments": [
            {
                "exchangeSegment": exchange_segment,
                "securityId": str(security_id)
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            # Dhan API ரெஸ்பான்ஸிலிருந்து LTP மதிப்பை எடுத்தல்
            return data.get("data", {}).get(str(security_id), {}).get("ltp", 0.0)
        else:
            print(f"Dhan LTP API Failed: {response.text}")
            return 0.0
    except Exception as e:
        print(f"Error fetching Dhan LTP: {e}")
        return 0.0

# ------------------------------------------
# 4. Phase 1: பிரீ-மார்க்கெட் க்ளோசிங் டேட்டா கணக்கீடு
# ------------------------------------------
def run_pre_market_logic():
    print("Running Pre-Market / Post-Market analysis via Dhan API...")
    global PRE_MARKET_SELECTED_STRIKES
    
    for stock in STOCKS_LIST:
        try:
            # TODO: Dhan Security ID-களைக் கண்டறிந்து க்ளோசிங் LTP எடுக்க வேண்டும்
            # இப்போதைக்கு டெஸ்டிங்கிற்காக உங்களுடைய அல்காரிதம் ரன் ஆக டம்மி மதிப்புகள்:
            call_ltp_close = 171.70 
            put_ltp_close = 158.10
            strike_price = 6800  
            
            # Step 1 & 2: Difference <= Strike Gap / 2
            diff = abs(call_ltp_close - put_ltp_close)
            if diff <= (STRIKE_GAP / 2):
                PRE_MARKET_SELECTED_STRIKES[stock] = {
                    "selected_strike": strike_price,
                    "close_diff": diff
                }
                print(f"Pre-Market Setup Done for {stock}: Selected Strike {strike_price}")
        except Exception as e:
            print(f"Error in Pre-market setup for {stock}: {e}")

# ------------------------------------------
# 5. Phase 2: காலை 9:15 மணிக்கு லைவ் மார்க்கெட் கண்காணிப்பு
# ------------------------------------------
def monitor_live_market():
    print("Live Market Monitoring Started...")
    
    for stock, setup in PRE_MARKET_SELECTED_STRIKES.items():
        try:
            selected_strike = setup["selected_strike"]
            
            # TODO: Dhan API மூலம் லைவ் LTP பெறப்படும்
            # இப்போதைக்கு டெஸ்டிங்கிற்காக டம்மி மதிப்புகள்:
            call_ltp_live = 83.50  
            put_ltp_live = 77.35  
            
            # Step 3: Average & Rounding to nearest Strike Gap
            avg_ltp = (call_ltp_live + put_ltp_live) / 2
            rounded_value = round(avg_ltp / STRIKE_GAP) * STRIKE_GAP
            
            # Step 4: Call Strike & Put Strike
            call_strike = selected_strike - rounded_value
            put_strike = selected_strike + rounded_value
            
            # Step 5: Adjusted Value Check
            live_diff = abs(call_ltp_live - put_ltp_live)
            if put_ltp_live > call_ltp_live:
                adjusted_value = selected_strike - live_diff
            else:
                adjusted_value = selected_strike + live_diff
                
            # Step 6: Call Difference & Put Difference
            call_diff = adjusted_value - call_strike
            put_diff = put_strike - adjusted_value
            
            # Step 7: டெலிகிராமிற்கு லைவ் சிக்னல் அனுப்புதல்
            alert_msg = f"🚨 *LIVE DHAN OPTION SIGNAL: {stock}* 🚨\n\n" \
                        f"🎯 Selected Strike (Yesterday): {selected_strike}\n" \
                        f"📞 Call Strike: {call_strike} | 📈 Put Strike: {put_strike}\n" \
                        f"⚖️ Adjusted Value: {adjusted_value:.2f}\n" \
                        f"🔹 Call Diff: {call_diff:.2f} | 🔸 Put Diff: {put_diff:.2f}"
            
            send_telegram(alert_msg)
            
        except Exception as e:
            print(f"Error in Live monitor for {stock}: {e}")

# ------------------------------------------
# 6. Dummy Web Server (Render பிளாக் ஆகாமல் இருக்க)
# ------------------------------------------
def start_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    handler = SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Dummy web server running on port {port}")
        httpd.serve_forever()

# ------------------------------------------
# 7. மெயின் எக்ஸிகியூஷன் (Main Control)
# ------------------------------------------
if __name__ == "__main__":
    # முதலில் Dhan இணைப்பை சரிபார்க்க ஒரு வெல்கம் மெசேஜ்
    send_telegram("🟢 Dhan Smart Option Bot Started Successfully! Monitoring Active.")
    
    # Pre-market கணக்கீடு
    run_pre_market_logic()
    
    # Render-க்காக டம்மி சர்வரை பேக்கிரவுண்டில் ரன் செய்கிறோம்
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    # காலை 9:15 முதல் மதியம் 3:30 வரை கண்காணிப்பு
    while True:
        now = datetime.now().time()
        if now >= datetime.strptime("09:15:00", "%H:%M:%S").time() and now <= datetime.strptime("15:30:00", "%H:%M:%S").time():
            monitor_live_market()
            time.sleep(60) # 1 நிமிட இடைவெளி
        else:
            print("Market is Closed. Waiting for next session...")
            time.sleep(300) # 5 நிமிட இடைவெளி
