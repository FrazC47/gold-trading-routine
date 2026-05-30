import yfinance as yf
import pandas as pd
import datetime
import requests
from io import StringIO

# Insert your Alpha Vantage API key here
ALPHA_VANTAGE_KEY = "A5XP1DKSB953D5L7"

def get_dual_macro_history():
    print("--- DUAL-LOOKBACK MACRO, DEMAND & FOREX REGIME ---")
    
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=40)
    
    assets = {
        "Gold": "GC=F",
        "DXY": "DX-Y.NYB",
        "10Y_Nominal": "^TNX",
        "GLD_ETF": "GLD"  
    }
    
    macro_df = pd.DataFrame()
    volume_df = pd.DataFrame()
    
    # 1. Fetch Yahoo Finance Data
    for name, ticker in assets.items():
        try:
            data = yf.Ticker(ticker)
            history = data.history(start=start, end=end)
            if not history.empty:
                history.index = history.index.tz_localize(None)
                macro_df[name] = history['Close']
                
                if name == "GLD_ETF":
                    volume_df['GLD_Volume'] = history['Volume']
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            
    # 2. Fetch FRED Data (10-Year Real Yield) via direct CSV endpoint
    try:
        fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
        fred_resp = requests.get(fred_url, timeout=15)
        fred_df = pd.read_csv(StringIO(fred_resp.text), parse_dates=['DATE'], index_col='DATE')
        fred_df = fred_df.loc[fred_df.index >= pd.Timestamp(start)]
        fred_df = fred_df.replace('.', float('nan')).dropna()
        fred_df['DFII10'] = fred_df['DFII10'].astype(float)
        macro_df['10Y_Real'] = fred_df['DFII10']
    except Exception as e:
        print(f"Error fetching FRED data: {e}")

    # 3. Fetch Alpha Vantage Data (EUR/USD Forex)
    try:
        url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url)
        av_data = response.json()
        
        if "Time Series FX (Daily)" in av_data:
            fx_daily = av_data["Time Series FX (Daily)"]
            fx_df = pd.DataFrame.from_dict(fx_daily, orient='index')
            fx_df.index = pd.to_datetime(fx_df.index)
            fx_df = fx_df.sort_index()
            # Extract closing prices
            macro_df['EUR_USD'] = fx_df['4. close'].astype(float)
        else:
            print("Error: Alpha Vantage limit reached or invalid API key.")
    except Exception as e:
        print(f"Error fetching Alpha Vantage data: {e}")

    # Combine and clean data
    combined_df = pd.concat([macro_df, volume_df], axis=1).dropna()
    
    # Extract the time windows
    regime_20d = combined_df.tail(20)
    momentum_5d = combined_df.tail(5)
    
    format_dict = {
        'Gold': '{:,.2f}'.format,
        'DXY': '{:.2f}'.format,
        '10Y_Nominal': '{:.2f}%'.format,
        '10Y_Real': '{:.2f}%'.format,
        'GLD_ETF': '${:,.2f}'.format,
        'GLD_Volume': '{:,.0f}'.format,
        'EUR_USD': '{:.4f}'.format
    }

    print("\n[20-DAY MACRO REGIME (THE TREND)]")
    print("Context: The structural monthly macroeconomic environment, ETF demand, and Forex flows.")
    print(regime_20d.to_string(formatters=format_dict))
    
    print("\n[5-DAY MOMENTUM TRAJECTORY (THE VELOCITY)]")
    print("Context: Immediate directional strength, short-term shocks, and ETF flows.")
    print(momentum_5d.to_string(formatters=format_dict))

if __name__ == "__main__":
    get_dual_macro_history()
