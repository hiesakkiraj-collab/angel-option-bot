import os
import time
from dhanhq.marketfeed import DhanFeed

# Render Environment Variables-ல் இருந்து விபரங்களை எடுக்கிறது
client_id = os.environ.get("DHAN_CLIENT_ID")
access_token = os.environ.get("DHAN_ACCESS_TOKEN")

def get_live_market_data():
    # 3045 = SBIN (NSE Equity)
    # WebSocket-க்கு செக்மென்ட் மற்றும் செக்யூரிட்டி ஐடி அவசியம்
    instruments = [("NSE_EQ", 3045)] 
    
    def on_connect(instance):
        instance.subscribe(instruments)
        print("✅ Connected to Dhan Feed!")
        
    def on_message(instance, message):
        print("📊 RECEIVED DATA:", message)

    # DhanFeed-ஐ ரன் செய்கிறோம்
    dhan = DhanFeed(client_id, access_token, instruments, on_connect, on_message)
    dhan.run_forever()

if __name__ == "__main__":
    # ஆப் வெளியேறாமல் இருக்க மெயின் லூப்
    try:
        get_live_market_data()
        while True:
            time.sleep(1)
    except Exception as e:
        print(f"❌ Error in main loop: {e}")
