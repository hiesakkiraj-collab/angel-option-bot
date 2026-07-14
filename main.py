import time
import requests
from datetime import datetime
from SmartApi import SmartConnect

# ==========================================
# உங்களது விபரங்களை இங்கே உள்ளீடு செய்யவும்
# ==========================================
API_KEY = "WW0IXyom"       # உங்க Angel One API Key
CLIENT_ID = "REEG1358"   # உங்க Angel One Client ID
PASSWORD = "1995"     # உங்க Angel One Login Password
TOTP_KEY = "3VEUGQ5Y12TK6AIEUTMVRX3CXE"       # உங்க SmartAPI-ல் இருக்கும் TOTP Secret Key

TELEGRAM_BOT_TOKEN = "8911103845:AAFY1jtuAgjdVOqPAR1hz29K2zmYcoBWp4"
TELEGRAM_CHAT_ID = "8479748092"

# 210 ஸ்டாக்குகளின் பட்டியல் (உதாரணத்திற்கு சில கொடுக்கப்பட்டுள்ளது, இதில் உங்கள் 210 ஸ்டாக்குகளை சேர்க்கலாம்)
STOCKS_LIST = ["RELIANCE", "TCS", "INFY", "SBIN", "HDFCBANK", "ICICIBANK", "TATAMOTORS"]
STRIKE_GAP = 50  # ஸ்டாக்கிற்கு ஏத்த மாதிரி இதையும் மாற்றிக்கொள்ளலாம்

# குளோபல் மெமரி (நேற்றைய முடிவில் தேர்வு செய்யப்பட்ட ஸ்ட்ரைக்குகளை சேமிக்க)
PRE_MARKET_SELECTED_STRIKES = {}

# Angel One API கனெக்ஷன்
obj = SmartConnect(api_key=API_KEY)
data = obj.generateSession(CLIENT_ID, PASSWORD, TOTP_KEY)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# Phase 1: மார்க்கெட் இல்லாத நேரத்தில் (Post/Pre-Market) ஆப்ஷன் செயின் க்ளோசிங் டேட்டா கணக்கீடு
def run_pre_market_logic():
    print("Running Pre-Market / Post-Market analysis...")
    global PRE_MARKET_SELECTED_STRIKES
    
    for stock in STOCKS_LIST:
        try:
            # இங்கு Angel One API மூலம் நேற்றைய ஆப்ஷன் செயின் க்ளோசிங் டேட்டா எடுக்கப்படும்
            # (உதாரண கணக்கீட்டிற்காக மாதிரி வேல்யூக்கள் கொடுக்கப்பட்டுள்ளது, API Response-ல் இருந்து இது மாறும்)
            # உதாரணத்திற்கு SBIN-ன் நேற்றைய Close LTP விபரங்கள்
            call_ltp_close = 171.70 
            put_ltp_close = 158.10
            strike_price = 6800  
            
            # Step 1 & 2: Difference <= Strike Gap / 2
            diff = abs(call_ltp_close - put_ltp_close)
            if diff <= (STRIKE_GAP / 2):
                # இந்த ஸ்ட்ரைக் தகுதியானது எனில் மெமரியில் சேமித்துக் கொள்
                PRE_MARKET_SELECTED_STRIKES[stock] = {
                    "selected_strike": strike_price,
                    "close_diff": diff
                }
                print(f"Pre-Market Setup Done for {stock}: Selected Strike {strike_price}")
        except Exception as e:
            print(f"Error in Pre-market setup for {stock}: {e}")

# Phase 2: காலை 9:15 மணிக்கு லைவ் மார்க்கெட்டில் கண்காணித்தல்
def monitor_live_market():
    print("Live Market Monitoring Started...")
    
    for stock, setup in PRE_MARKET_SELECTED_STRIKES.items():
        try:
            selected_strike = setup["selected_strike"]
            
            # Angel One API மூலம் இந்த குறிப்பிட்ட செலக்ட் செய்யப்பட்ட ஸ்ட்ரைக்கின் LIVE LTP எடுக்கப்படும்
            # (உதாரணமாக லைவ் மார்க்கெட்டில் வரும் டேட்டா)
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
            alert_msg = f"🚨 *LIVE OPTION SIGNAL: {stock}* 🚨\n\n" \
                        f"🎯 Selected Strike (Based on Yesterday): {selected_strike}\n" \
                        f"📞 Call Strike: {call_strike} | 📈 Put Strike: {put_strike}\n" \
                        f"⚖️ Adjusted Value: {adjusted_value:.2f}\n" \
                        f"🔹 Call Diff: {call_diff:.2f} | 🔸 Put Diff: {put_diff:.2f}"
            
            send_telegram(alert_msg)
            
        except Exception as e:
            print(f"Error in Live monitor for {stock}: {e}")

# முதன்மை இயக்கம் (Execution Control)
if __name__ == "__main__":
    # 1. முதலில் நேற்றைய க்ளோசிங் டேட்டாவை கணக்கிட்டு ஸ்ட்ரைக்கை லாக் செய்கிறது
    run_pre_market_logic()
    
    # 2. காலை 9:15 வரை காத்திருந்து பின்னர் லைவ் மார்க்கெட்டை கண்காணிக்கிறது
    while True:
        now = datetime.now().time()
        # காலை 09:15 முதல் மதியம் 03:30 வரை மட்டும் லைவ் ரன் செய்ய
        if now >= datetime.strptime("09:15:00", "%H:%M:%S").time() and now <= datetime.strptime("15:30:00", "%H:%M:%S").time():
            monitor_live_market()
            time.sleep(60) # ஒவ்வொரு 1 நிமிடத்திற்கும் லைவ் டேட்டாவை செக் செய்யும்
        else:
            print("Market is Closed. Waiting for next session...")
            time.sleep(300) # மார்க்கெட் இல்லாத நேரத்தில் 5 நிமிடத்திற்கு ஒருமுறை செக் செய்யும்
