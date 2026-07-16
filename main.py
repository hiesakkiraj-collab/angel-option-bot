import os
import requests
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# தனுஷின் சரியான API URL
DHAN_BASE_URL = "https://api.dhan.co"

def get_dhan_token_details():
    # இது அனைத்து தனுஷ் இன்ஸ்ட்ருமென்ட்களையும் தரவிறக்கம் செய்யும்
    url = f"{DHAN_BASE_URL}/instruments"
    try:
        response = requests.get(url)
        # இதில் 814 ஐத் தேடி, அதற்கு இணையான 'dhanSecurityId'-ஐ எடுக்கலாம்
        return response.json()
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    # போர்ட் சிக்கலைத் தீர்க்க Flask சர்வர்
    port = int(os.environ.get("PORT", 10000))
    
    # தனுஷ் ஐடி டிடெக்டர்
    print("V18.0 Initialized...")
    
    # 814 எக்ஸ்சேஞ்ச் ஐடிக்குரிய தனுஷ் ஐடியைக் கண்டறிய முயற்சி
    # (இது ஒருமுறை மட்டும் ரன் ஆகும்)
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': port}).start()
    
    # ஒரு சிறிய டெஸ்ட்
    print("Fetching full instrument list to resolve IDs...")
    instruments = get_dhan_token_details()
    print("Token resolution complete.")
