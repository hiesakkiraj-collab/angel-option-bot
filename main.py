import os
from dhanhq import marketfeed

# Render Environment Variables-ல் இருந்து விபரங்களை எடுக்கும்
client_id = os.environ.get("DHAN_CLIENT_ID")
access_token = os.environ.get("DHAN_ACCESS_TOKEN")

# இது தான் தனுஷ் கொடுக்கும் அதிகாரப்பூர்வ வழி
def get_live_market_data():
    # 3045 = SBIN (NSE Equity)
    instruments = [("NSE_EQ", 3045)]
    
    def on_connect(instance):
        instance.subscribe(instruments)
        print("Connected to Dhan Feed!")
        
    def on_message(instance, message):
        print("RECEIVED DATA:", message)

    dhan = marketfeed.DhanFeed(client_id, access_token, instruments, on_connect, on_message)
    dhan.run_forever()

if __name__ == "__main__":
    get_live_market_data()
