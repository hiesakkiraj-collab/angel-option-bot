import os
import requests
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading

# ரகசிய விபரங்கள் (Render Environment Variables-லிருந்து எடுக்கப்படும்)
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

IST = timezone(timedelta(hours=5, minutes=30))

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def test_dhan_api():
    if not ACCESS_TOKEN:
        msg = "❌ Error: DHAN_ACCESS_TOKEN is missing in Render Environment Variables!"
        print(msg)
        send_telegram(msg)
        return

    headers = {
        'access-token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    
    # SBIN-ன் ஒரு குறிப்பிட்ட ஆப்ஷன் செக்யூரிட்டி ஐடி (821584)
    payload = {
        "instruments": [
            {
                "exchangeSegment": "NSE_FO",
                "securityId": "821584"
            }
        ]
    }
    
    try:
        print("Testing Connection to Dhan API...")
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        # லாக்ஸ் மற்றும் டெலிகிராமில் முடிவுகளைக் காட்டுதல்
        status_code = response.status_code
        try:
            res_json = response.json()
        except:
            res_json = response.text

        log_msg = f"🔍 *Dhan API Test Result:*\n\n" \
                  f"*Status Code:* {status_code}\n" \
                  f"*Response:* `{res_json}`"
                  
        print(log_msg)
        send_telegram(log_msg)
        
    except Exception as e:
        err_msg = f"❌ API Request Failed: {e}"
        print(err_msg)
        send_telegram(err_msg)

# Render-க்காக போர்ட் ரன் செய்ய வேண்டும்
def start_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    handler = SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    # டெஸ்ட் ரன் செய்கிறோம்
    test_dhan_api()
    
    # வெப் சர்வர் ஸ்டார்ட்
    start_dummy_server()
