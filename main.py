import os
import time
import requests
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading
from datetime import datetime

# ==========================================
# 1. உங்களுடைய DHAN மற்றும் TELEGRAM விபரங்கள்
# ==========================================
# இங்கே உங்களுடைய உண்மையான Dhan விபரங்களை உள்ளீடு செய்யவும்
CLIENT_ID = "1105569288"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzg0MTQyNTkzLCJpYXQiOjE3ODQwNTYxOTMsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA1NTY5Mjg4In0.zLZOd7qRCdqJZYnXGBgze0GqCnwWO33N0_ZpHSSnJT5isjWSqaBZbPBH3wElOUPTEOf6hqLqKQllAi18mx4cOQ"

# உங்களுடைய டெலிகிராம் விபரங்கள் (முன்பே சரியாக இருந்தது)
TELEGRAM_BOT_TOKEN = "8911103845:AAFY1jtuAgjdV0qPAR1hz9K2zmYcoBWp4"
TELEGRAM_CHAT_ID = "8479748092"

# ------------------------------------------
# 2. Dummy Web Server (Render இன்ஆக்டிவ் ஆகாமல் இருக்க)
# ------------------------------------------
def run_dummy_server():
    PORT = int(os.environ.get("PORT", 8000))
    Handler = SimpleHTTPRequestHandler
    # பிளாட்பார்ம் போர்ட் ரீயூஸ் செய்ய allow_reuse_address செட் செய்யப்பட்டுள்ளது
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Dummy web server running on port {PORT}")
        httpd.serve_forever()

# சர்வரை பின்னணியில் (Background Thread) இயக்குதல்
threading.Thread(target=run_dummy_server, daemon=True).start()

# ------------------------------------------
# 3. Telegram அலர்ட் அனுப்பும் ஃபங்க்ஷன்
# ------------------------------------------
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Telegram alert sent successfully!")
        else:
            print(f"Telegram failed: {response.text}")
    except Exception as e:
        print("Telegram communication error:", e)

# ------------------------------------------
# 4. Dhan API கனெக்ஷன் சரிபார்ப்பு
# ------------------------------------------
def check_dhan_connection():
    headers = {
        'access-token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }
    try:
        # Dhan Profile API-ஐ அழைத்து டோக்கன் சரியாக உள்ளதா என சரிபார்த்தல்
        response = requests.get("https://api.dhan.co/v2/profile", headers=headers)
        if response.status_code == 200:
            profile = response.json()
            name = profile.get('clientName', 'Dhan User')
            msg = f"🟢 Dhan Trading Bot Connected!\nWelcome back, {name}."
            print(msg)
            send_telegram_message(msg)
            return True
        else:
            error_msg = f"🔴 Dhan Connection Failed!\nStatus Code: {response.status_code}\nResponse: {response.text}"
            print(error_msg)
            send_telegram_message(error_msg)
            return False
    except Exception as e:
        print("Error connecting to Dhan API:", e)
        return False

# ------------------------------------------
# 5. மெயின் லூப் (Main Execution)
# ------------------------------------------
def main():
    print("Initializing Dhan Strategy Bot...")
    time.sleep(2) # சர்வர் நிலைபெற குட்டி பிரேக்
    
    # முதலில் தன் ஏபிஐ இணைப்பைச் சோதிக்கவும்
    connected = check_dhan_connection()
    
    if not connected:
        print("Bot halting due to connection issues. Please check your Access Token.")
        # இணைப்பு தோல்வியுற்றாலும் ரெண்டர் சர்வர் மூடாமல் இருக்க லூப்
        while True:
            time.sleep(3600)

    # வெற்றிகரமாக இணைக்கப்பட்டால் மார்க்கெட் கண்காணிப்பு லூப் தொடங்கும்
    while True:
        now = datetime.now()
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Bot is active. Scanning market data...")
        
        # இப்போதைக்கு மார்க்கெட் மூடியிருப்பதால் காத்திருக்க வைப்போம்
        # லைவ் ஸ்ட்ரேட்டஜி மற்றும் இண்டிகேட்டர் கோடுகளை நாம் அடுத்து இங்கே சேர்க்கலாம்
        time.sleep(60)

if __name__ == "__main__":
    main()
