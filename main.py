import os
import requests
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading

# 1. முதலில் சர்வர் ரன் ஆகிறதா என்று பார்ப்போம்
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting server on port {port}")
    class MyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is active!")
    httpd = HTTPServer(('', port), MyHandler)
    httpd.serve_forever()

# 2. த்ரெடிங் மூலம் சர்வரை ஸ்டார்ட் செய்கிறோம்
threading.Thread(target=run_dummy_server, daemon=True).start()

# 3. பாட் லாஜிக் (சின்ன டெஸ்ட்)
print("Bot started, waiting for market data...")
while True:
    print("Bot is looping...")
    time.sleep(60)
