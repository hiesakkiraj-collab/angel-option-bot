import os
import requests
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading

# ரகசிய விபரங்கள் (Render Environment Variables-லிருந்து எடுக்கப்படும்)
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")
DHAN_CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
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
    if not ACCESS_TOKEN or not DHAN_CLIENT_ID:
        msg = "❌ Error: DHAN_ACCESS_TOKEN or DHAN_CLIENT_ID is missing in Render Environment Variables!"
        print(msg)
        send_telegram(msg)
        return

    # Dhan HQ API-க்கு தேவையான Headers மற்றும் சரியான Client ID இணைப்பு
    url = "https://api.dhan.co/v2/holdings"  # API சரியாக வேலை செய்கிறதா எனச் சோதிக்க Holdings End-point
    headers = {
        "access-token": ACCESS_TOKEN,
        "client-id": DHAN_CLIENT_ID,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        status_code = response.status_code
        
        try:
            res_data = response.json()
        except:
            res_data = response.text

        # டெலிகிராமிற்கு ரிசல்ட்டை அனுப்புதல்
        bot_msg = f"🔍 *Dhan API Test Result:*\n\n*Status Code:* {status_code}\n*Response:* `{res_data}`"
        send_telegram(bot_msg)

    except Exception as e:
        send_telegram(f"❌ API Request Exception: {str(e)}")

# Render தளம் எப்போதுமே Active-ஆக இருக்க ஒரு எளிய Web Server போர்ட் (Port Binding)
class HealthCheckHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is Running Perfectly!")

def run_server():
    port = int(os.environ.get("PORT", 8080))
    with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
        print(f"Health check server running on port {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Web server-ஐ தனி திரெட்டில் (Thread) இயக்குதல்
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("Starting Dhan API Test...")
    # பாட் ரன் ஆனதும் முதலில் API-ஐ டெஸ்ட் செய்யும்
    test_dhan_api()
    
    # மெயின் திரெட்டை உயிர்ப்புடன் வைத்திருக்க
    import time
    while True:
        time.sleep(3600)
