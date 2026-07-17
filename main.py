import os
import time
import threading
import requests
import pandas as pd
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ==========================
# DHAN API
# ==========================

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

CSV_FILE = "api-scrip-master-detailed.csv"

# ==========================
# Dummy Web Server
# ==========================

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot Running")

    HTTPServer(("", port), Handler).serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================
# Load CSV
# ==========================

print("Loading Instrument CSV...")

df = pd.read_csv(CSV_FILE, low_memory=False)

print("CSV Loaded :", len(df), "rows")

# ==========================
# Find Security ID
# ==========================

def get_security_id(strike, option_type):

    option_type = option_type.upper()

    row = df[
        (df["UNDERLYING_SYMBOL"] == "SBIN") &
        (df["STRIKE_PRICE"] == strike) &
        (df["OPTION_TYPE"] == option_type)
    ]

    if row.empty:
        return None

    return str(row.iloc[0]["SECURITY_ID"])

# ==========================
# Quote
# ==========================

def fetch_closed_price():

    ce_id = get_security_id(1000, "CALL")
    pe_id = get_security_id(1000, "PUT")

    print("-----------------------------------")
    print("CALL Security ID :", ce_id)
    print("PUT  Security ID :", pe_id)

    if ce_id is None or pe_id is None:
        print("Security ID not found")
        return

    url = "https://api.dhan.co/v2/marketfeed/quote"

    headers = {
        "access-token": ACCESS_TOKEN,
        "client-id": CLIENT_ID,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "NSE_FNO": [
            int(ce_id),
            int(pe_id)
        ]
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        print("Status :", response.status_code)
        print(response.text)

        if response.status_code == 200:

            data = response.json()

            print("SUCCESS")
            print(data)

        else:

            print("API Error")

    except Exception as e:

        print("Exception :", e)

# ==========================
# MAIN
# ==========================

print("Bot Started...")

while True:

    fetch_closed_price()

    time.sleep(60)
