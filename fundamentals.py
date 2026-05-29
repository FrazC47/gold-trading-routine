import yfinance as yf
import pandas as pd

def get_market_analysis():
    print("--- ITERATION 3: MOMENTUM ANALYSIS ---")
    assets = {
        "Gold (GC=F)": "GC=F",
        "US Dollar Index (DXY)": "DX-Y.NYB",
        "US 10Y Yield (^TNX)": "^TNX"
    }
    
    for name, ticker in assets.items():
        try:
            data = yf.Ticker(ticker)
            # Fetch 5 days to ensure we have enough history for accurate closing comparison
            history = data.history(period="5d")
            
            if len(history) >= 2:
                latest_close = history['Close'].iloc[-1]
                prev_close = history['Close'].iloc[-2]
                
                # Calculate percent change
                pct_change = ((latest_close - prev_close) / prev_close) * 100
                direction = "🔺" if pct_change > 0 else "🔻"
                
                print(f"{name}: {latest_close:.2f} ({direction} {pct_change:+.2f}%)")
            else:
                print(f"Insufficient history to calculate change for {name}")
        except Exception as e:
            print(f"Error analyzing {name}: {e}")

if __name__ == "__main__":
    get_market_analysis()
