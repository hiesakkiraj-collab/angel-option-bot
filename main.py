import os
import requests
import threading
import pandas as pd
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_security_id_from_csv(strike, option_type):
    try:
        df = pd.read_csv('api-scrip-master-detailed.csv', low_memory=False)
        target_strike = int(strike)
        filtered = df[(df['STRIKE_PRICE'] == target_strike) & (df['SYMBOL_NAME'].str.contains(option_type))]
        
        if not filtered.empty:
            return str(filtered['SECURITY_ID'].iloc[0])
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def fetch_closed_price():
    ce_id = get_security_id_from_csv(1000, "CE")
    pe_id = get_security_id_from_csv(1000, "PE")
    
    if not ce_id or not pe_id:
        return

    # தனுஷ் Quote API URL
    url = "https://api.dhan.co/quotes/snfe"
    headers = {'access-token': ACCESS_TOKEN, 'client-id': CLIENT_ID, 'Content-Type': 'application/json'}
    
    # Quote API-க்கு தேவையான payload
    payload = {
        "symbols": [
            {"exchangeSegment": "NSE_FNO", "securityId": ce_id},
            {"exchangeSegment": "NSE_FNO", "securityId": pe_id}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json().get("data", {})
        # Quote API-ல் 'lastPrice' அல்லது 'closePrice' என்று வரும்
        ce_price = data.get(ce_id, {}).get("lastPrice")
        pe_price = data.get(pe_id, {}).get("lastPrice")
        print(f"📊 CLOSED PRICE: CE (1000): {ce_price} | PE (1000): {pe_price}")
    else:
        print("API Error:", response.text)

# (run_dummy_server மற்றும் main loop பகுதி அப்படியே இருக்கட்டும்)
