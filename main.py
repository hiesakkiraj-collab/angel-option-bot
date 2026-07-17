def get_live_data_v2():
    url = "https://api.dhan.co/v2/marketfeed/ltp"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # இம்முறை securityId-ஐ எண்ணாக (integer) அனுப்பிப் பார்ப்போம்
    payload = {
        "symbols": [
            {
                "exchangeSegment": "NSE_EQ",
                "securityId": 3045
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        resp_json = response.json()
        print(f"FULL RESPONSE: {resp_json}")
        
        # டேட்டா உள்ளே இருக்கிறதா என்று பார்ப்போம்
        if 'data' in resp_json and resp_json['data']:
            print("✅ DATA RECEIVED:", resp_json['data'])
        else:
            print("⚠️ Data is empty, trying another security ID...")
            
    except Exception as e:
        print(f"Error: {e}")
