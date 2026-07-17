import os
from dhanhq.marketfeed import DhanFeed  # இந்த வரியை மட்டும் கவனமாக மாற்றவும்

# Render Environment Variables-ல் இருந்து விபரங்களை எடுக்கும்
client_id = os.environ.get("DHAN_CLIENT_ID")
access_token = os.environ.get("DHAN_ACCESS_TOKEN")

def get_live_market_data():
    # 3045 = SBIN (NSE Equity)
    # இதில் 'NSE_EQ' என செக்மென்ட்டை நேரடியாக ஸ்டிரிங்காக கொடுப்போம்
    instruments = [("NSE_EQ", 3045)] 
    
    def on_connect(instance):
        instance.subscribe(instruments)
        print("Connected to Dhan Feed!")
        
    def on_message(instance, message):
        print("RECEIVED DATA:", message)

    # நேரடியாக DhanFeed-ஐ பயன்படுத்துகிறோம்
    dhan = DhanFeed(client_id, access_token, instruments, on_connect, on_message)
    dhan.run_forever()

if __name__ == "__main__":
    get_live_market_data()
