import os
import requests
import pandas as pd
import io

def get_real_dhan_id():
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    response = requests.get(url, timeout=30)
    df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    
    # 🎯 V22.0: செக்மென்ட் மற்றும் சிம்பல் வைத்து சரியான வரியைத் தேடுதல்
    # NSE Equity-ல் SBIN ஐ தேடுவோம்
    sbin_row = df[(df['SM_SYMBOL_NAME'] == 'SBIN') & (df['SEM_EXM_EXCH_ID'] == 'NSE') & (df['SEM_SEGMENT'] == 'C')]
    
    # இங்கே ஒரு 'dhanSecurityId' காலம் இருக்கிறதா என்று பார்ப்போம்
    print("Columns found in DF:", df.columns.tolist())
    print("SBIN Data:\n", sbin_row[['SEM_TRADING_SYMBOL', 'SEM_SMST_SECURITY_ID']])

if __name__ == "__main__":
    get_real_dhan_id()
