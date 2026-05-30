import yfinance as yf
import pandas as pd
import datetime
import requests

ALPHA_VANTAGE_KEY = "A5XP1DKSB953D5L7"

def fetch_fred_series(series_id, start, end):
    """Fetch a FRED data series using direct API requests (no pandas_datareader)."""
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    url = (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&vintage_date={end_str}"
    )
    try:
        response = requests.get(url, timeout=15)
        from io import StringIO
        df = pd.read_csv(StringIO(response.text), parse_dates=['DATE'], index_col='DATE')
        df = df.replace('.', float('nan'))
        df = df.astype(float)
        df = df.loc[start_str:end_str]
        df.columns = [series_id]
        return df
    except Exception as e:
        print(f"FRED fetch error for {series_id}: {e}")
        return pd.DataFrame()

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

    # 2. Fetch FRED Data (10-Year Real Yield) via direct request
    try:
        real_yield_data = fetch_fred_series('DFII10', start, end)
        if not real_yield_data.empty:
            macro_df['10Y_Real'] = real_yield_data['DFII10']
        else:
            print("Warning: Could not fetch FRED real yield data.")
    except Exception as e:
        print(f"Error fetching FRED data: {e}")

    # 3. Fetch Alpha Vantage Data (EUR/USD Forex)
    try:
        url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url, timeout=15)
        av_data = response.json()

        if "Time Series FX (Daily)" in av_data:
            fx_daily = av_data["Time Series FX (Daily)"]
            fx_df = pd.DataFrame.from_dict(fx_daily, orient='index')
            fx_df.index = pd.to_datetime(fx_df.index)
            fx_df = fx_df.sort_index()
            macro_df['EUR_USD'] = fx_df['4. close'].astype(float)
        else:
            print("Alpha Vantage response:", av_data)
    except Exception as e:
        print(f"Error fetching Alpha Vantage data: {e}")

    # Combine and clean data
    combined_df = pd.concat([macro_df, volume_df], axis=1)
    # Drop rows where all core columns are NaN (but keep partial rows)
    combined_df = combined_df.dropna(subset=['Gold', 'DXY', '10Y_Nominal', 'GLD_ETF', 'GLD_Volume'])

    regime_20d = combined_df.tail(20)
    momentum_5d = combined_df.tail(5)

    def fmt_gold(v):
        try:
            return f"{v:,.2f}"
        except:
            return str(v)
    def fmt_dxy(v):
        try:
            return f"{v:.2f}"
        except:
            return str(v)
    def fmt_pct(v):
        try:
            return f"{v:.2f}%"
        except:
            return str(v)
    def fmt_gld(v):
        try:
            return f"${v:,.2f}"
        except:
            return str(v)
    def fmt_vol(v):
        try:
            return f"{v:,.0f}"
        except:
            return str(v)
    def fmt_fx(v):
        try:
            return f"{v:.4f}"
        except:
            return str(v)

    print("\n[20-DAY MACRO REGIME (THE TREND)]")
    print("Context: The structural monthly macroeconomic environment, ETF demand, and Forex flows.")
    print(regime_20d.to_string())

    print("\n[5-DAY MOMENTUM TRAJECTORY (THE VELOCITY)]")
    print("Context: Immediate directional strength, short-term shocks, and ETF flows.")
    print(momentum_5d.to_string())

    # Return data for further processing
    return regime_20d, momentum_5d

if __name__ == "__main__":
    get_dual_macro_history()
