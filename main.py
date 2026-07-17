def get_atm_option_data():
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json',
        'Accept': 'application/json' # இதைச் சேர்ப்பது முக்கியம்
    }
    
    payload = {
        "underlyingScri": 3045,  # தனுஷ் v2-ல் பெரும்பாலும் இந்த கீ தான் வேலை செய்யும்
        "underlyingSeg": "NSE_EQ"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        # JSON என்று மாற்றும் முன் என்ன வருகிறது என்று பார்ப்போம்
        if response.status_code == 200:
            print("✅ SUCCESS:", response.json())
        else:
            print(f"❌ API FAILED with status {response.status_code}")
            print("RAW RESPONSE:", response.text) # இதுதான் பிழைக்குக் காரணம் என்னவென்று காட்டும்
            
    except Exception as e:
        print(f"❌ Error: {e}")
