import requests
import os

# உங்கள் API விபரங்கள்
CLIENT_ID = os.environ.get("DHAN_CLIENT_ID")
ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN")

def get_atm_data(underlying_id):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        'access-token': ACCESS_TOKEN, 
        'client-id': CLIENT_ID, 
        'Content-Type': 'application/json'
    }
    
    # குறிப்பிட்ட அண்டர்லையிங் ஐடிக்கான ஆப்ஷன் செயின்
    payload = {
        "underlyingScri": underlying_id,
        "underlyingSeg": "IDX_I" # Index என்றால் IDX_I
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    # இதில் ATM ஸ்டிரைக் பிரைஸை மட்டும் பிரித்தெடுக்கலாம்
    # response-ல் 'data' பிரிவில் ஆப்ஷன் செயின் இருக்கும்
    return data

# பயன்பாடு:
# Nifty (13) அல்லது BankNifty (12) ஐடியைப் பயன்படுத்தவும்
print(get_atm_data(13))
