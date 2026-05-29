import yfinance as yf
import pandas as pd

def get_market_data():
    print("--- ITERATION 2: CORE MARKET DATA ---")
    assets = {
        "Gold (GC=F)": "GC=F",
        "US Dollar Index (DXY)": "DX-Y.NYB",
        "US 10Y Yield (^TNX)": "^TNX"
    }
    
    for name, ticker in assets.items():
        try:
            data = yf.Ticker(ticker)
            # Fetch 5 days of data to ensure we get the latest valid close
            history = data.history(period="5d")
            if not history.empty:
                latest_close = history['Close'].iloc[-1]
                print(f"{name}: {latest_close:.2f}")
            else:
                print(f"No data found for {name}")
        except Exception as e:
            print(f"Error fetching {name}: {e}")

if __name__ == "__main__":
    get_market_data()
