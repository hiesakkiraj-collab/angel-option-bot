import os
import time
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pandas as pd
import requests

CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

CSV_FILE = "api-scrip-master-detailed.csv"

# ---------------- Dummy Server ----------------

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot Running")

    HTTPServer(("", port), Handler).serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

# ---------------- Load CSV ----------------

df = pd.read_csv(CSV_FILE, low_memory=False)

print("CSV Loaded :", len(df), "rows")

# ---------------- Get Security ID ----------------

def get_security_id(strike, option_type):

    data = df[
        (df["UNDERLYING_SYMBOL"].astype(str).str.strip() == "SBIN")
        & (df["STRIKE_PRICE"].astype(float) == float(strike))
        & (df["OPTION_TYPE"].astype(str).str.strip() == option_type)
    ].copy()

    if data.empty:
        return None

    # Nearest expiry
    data["EXP"] = pd.to_datetime(
        data["SM_EXPIRY_DATE"],
        format="%d/%m/%Y",
        errors="coerce"
    )

    data = data.sort_values("EXP")

    return str(data.iloc[0]["SECURITY_ID"])

# ---------------- Quote ----------------

def fetch_closed_price():

    ce_id = get_security_id(1000, "CE")
    pe_id = get_security_id(1000, "PE")

    print("--------------------------------")
    print("CE ID :", ce_id)
    print("PE ID :", pe_id)

    if ce_id is None or pe_id is None:
        print("Security ID Not Found")
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

        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        print("Status :", r.status_code)
        print("Response :", r.text)

    except Exception as e:
        print(e)

# ---------------- Main ----------------

print("Bot Started")

while True:
    fetch_closed_price()
    time.sleep(60)
