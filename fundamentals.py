#!/usr/bin/env python3
"""
fundamentals.py — Gold macro briefing generator
Data source: Google Sheets (persistent) + yfinance/FRED (gap-fill fallback)
"""

import sys
import os
import datetime
import pandas as pd
import requests
import io

# ─── ATTEMPT GOOGLE SHEETS IMPORT ────────────────────────────────────
try:
    import sheets_db as db
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    print("⚠️  sheets_db.py not found — falling back to direct yfinance fetch.")
    import yfinance as yf

# ─── ALPHA VANTAGE KEY ───────────────────────────────────────────────
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "A5XP1DKSB953D5L7")

# ─── MAIN ANALYSIS ───────────────────────────────────────────────────
def get_dual_macro_history():
    print("=" * 60)
    print("DUAL-LOOKBACK MACRO, DEMAND & FOREX REGIME")
    print("=" * 60)
    
    end = datetime.datetime.now()
    start_40d = end - datetime.timedelta(days=40)
    
    if SHEETS_AVAILABLE:
        # ── CLOUD PATH: Read from Sheets, fill gaps ─────────────────
        data = db.sync_all()
        
        # Build combined DataFrames from Sheets data
        gold = data["GC=F"].set_index("date")[["close"]].rename(columns={"close": "Gold"})
        dxy = data["DX-Y.NYB"].set_index("date")[["close"]].rename(columns={"close": "DXY"})
        tnx = data["^TNX"].set_index("date")[["close"]].rename(columns={"close": "10Y_Nominal"})
        gld_price = data["GLD"].set_index("date")[["close"]].rename(columns={"close": "GLD_ETF"})
        gld_vol = data["GLD"].set_index("date")[["volume"]].rename(columns={"volume": "GLD_Volume"})
        
        # FRED real yield
        fred_df = data["FRED"].set_index("date")[["dfii10"]].rename(columns={"dfii10": "10Y_Real"})
        
        # EUR/USD — try Sheets first, fallback to AV
        if "EURUSD=X" in data and not data["EURUSD=X"].empty:
            eur = data["EURUSD=X"].set_index("date")[["close"]].rename(columns={"close": "EUR_USD"})
        else:
            eur = fetch_alpha_vantage_fx(start_40d)
        
        # Combine
        macro_df = pd.concat([gold, dxy, tnx, fred_df, gld_price, eur], axis=1)
        volume_df = gld_vol
        
        # Filter to 40 days for display
        cutoff = (end - datetime.timedelta(days=40)).date()
        macro_df.index = pd.to_datetime(macro_df.index)
        volume_df.index = pd.to_datetime(volume_df.index)
        macro_df = macro_df[macro_df.index >= pd.Timestamp(cutoff)]
        if not volume_df.empty:
            volume_df = volume_df[volume_df.index >= pd.Timestamp(cutoff)]
    
    else:
        # ── FALLBACK PATH: Direct fetch (original behavior) ─────────
        print("--- FALLBACK: Fetching directly from yfinance/FRED/AV ---")
        macro_df, volume_df = fetch_all_direct(start_40d, end)
    
    # ── EXTRACT WINDOWS ───────────────────────────────────────────
    combined_df = pd.concat([macro_df, volume_df], axis=1).dropna()
    regime_20d = combined_df.tail(20)
    momentum_5d = combined_df.tail(5)
    
    # ── FORMAT AND PRINT ──────────────────────────────────────────
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
    
    # ── KEY LEVELS FOR BRIEFING ───────────────────────────────────
    print("\n" + "=" * 60)
    print("KEY LEVELS FOR DAILY RISK RULES")
    print("=" * 60)
    
    dxy_5d_high = momentum_5d["DXY"].max()
    dxy_5d_high_date = momentum_5d["DXY"].idxmax()
    real_5d_high = momentum_5d["10Y_Real"].max()
    real_5d_high_date = momentum_5d["10Y_Real"].idxmax()
    gold_5d_low = momentum_5d["Gold"].min()
    gold_5d_low_date = momentum_5d["Gold"].idxmin()
    gold_5d_open = momentum_5d["Gold"].iloc[0]
    gld_vol_5d_avg = momentum_5d["GLD_Volume"].mean() if "GLD_Volume" in momentum_5d else 0
    
    print(f"DXY 5-day high:     {dxy_5d_high:.2f} (on {dxy_5d_high_date})")
    print(f"Real Yield 5-day high: {real_5d_high:.2f}% (on {real_5d_high_date})")
    print(f"Gold 5-day low:     ${gold_5d_low:,.2f} (on {gold_5d_low_date})")
    print(f"Gold 5-day open:    ${gold_5d_open:,.2f} (on {momentum_5d.index[0]})")
    print(f"GLD 5-day avg vol:  {gld_vol_5d_avg:,.0f}")
    print("=" * 60)

# ─── DIRECT FETCH FUNCTIONS (fallback) ───────────────────────────────
def fetch_all_direct(start, end):
    """Original fetch logic — used when sheets_db is unavailable."""
    assets = {
        "Gold": "GC=F",
        "DXY": "DX-Y.NYB",
        "10Y_Nominal": "^TNX",
        "GLD_ETF": "GLD"
    }
    macro_df = pd.DataFrame()
    volume_df = pd.DataFrame()
    
    for name, ticker in assets.items():
        try:
            data = yf.Ticker(ticker)
            history = data.history(start=start, end=end)
            if not history.empty:
                history.index = history.index.tz_localize(None)
                macro_df[name] = history["Close"]
                if name == "GLD_ETF":
                    volume_df["GLD_Volume"] = history["Volume"]
        except Exception as e:
            print(f"Error fetching {name}: {e}")
    
    # FRED
    try:
        fred_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
        fred_csv = pd.read_csv(io.StringIO(requests.get(fred_url, timeout=15).text))
        date_col = fred_csv.columns[0]
        fred_csv[date_col] = pd.to_datetime(fred_csv[date_col])
        fred_csv = fred_csv.set_index(date_col)
        fred_csv = fred_csv[fred_csv.index >= pd.Timestamp(start)]
        val_col = fred_csv.columns[0]
        fred_csv[val_col] = pd.to_numeric(fred_csv[val_col], errors="coerce")
        macro_df["10Y_Real"] = fred_csv[val_col]
    except Exception as e:
        print(f"Error fetching FRED: {e}")
    
    # Alpha Vantage EUR/USD
    eur_df = fetch_alpha_vantage_fx(start)
    if not eur_df.empty:
        macro_df["EUR_USD"] = eur_df["EUR_USD"]
    
    return macro_df, volume_df

def fetch_alpha_vantage_fx(start):
    """Fetch EUR/USD from Alpha Vantage. Returns DataFrame with EUR_USD column."""
    try:
        url = (f"https://www.alphavantage.co/query?"
               f"function=FX_DAILY&from_symbol=EUR&to_symbol=USD"
               f"&apikey={ALPHA_VANTAGE_KEY}")
        resp = requests.get(url, timeout=15)
        data = resp.json()
        
        if "Time Series FX (Daily)" in data:
            fx = pd.DataFrame.from_dict(data["Time Series FX (Daily)"], orient="index")
            fx.index = pd.to_datetime(fx.index)
            fx = fx.sort_index()
            fx = fx[fx.index >= pd.Timestamp(start)]
            df = pd.DataFrame({"EUR_USD": fx["4. close"].astype(float)})
            return df
        else:
            print("Alpha Vantage: limit reached or no data")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching Alpha Vantage: {e}")
        return pd.DataFrame()

# ─── ARCHIVE MODE ────────────────────────────────────────────────────
def archive_briefing():
    """Read briefing_final.md and archive to Google Sheets."""
    if not SHEETS_AVAILABLE:
        print("❌ Cannot archive — sheets_db.py not available.")
        sys.exit(1)
    
    if not os.path.exists("briefing_final.md"):
        print("❌ briefing_final.md not found. Save the briefing text first.")
        sys.exit(1)
    
    with open("briefing_final.md", "r") as f:
        full_text = f.read().strip()
    
    if not full_text:
        print("❌ briefing_final.md is empty.")
        sys.exit(1)
    
    # Extract bias from first line
    lines = full_text.split("\n")
    bias = "NEUTRAL"
    for line in lines[:10]:
        if "BUYING" in line.upper() or "LONG" in line.upper():
            bias = "BUYING"
        elif "SHORT" in line.upper():
            bias = "SHORTING"
        elif "STAYING OUT" in line.upper() or "NEUTRAL" in line.upper():
            bias = "NEUTRAL"
    
    # Parse key levels from the text (best-effort)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Try to read the synced data to get exact latest prices
    try:
        data = db.sync_all()
        gold_latest = float(data["GC=F"]["close"].iloc[-1]) if not data["GC=F"].empty else 0
        dxy_latest = float(data["DX-Y.NYB"]["close"].iloc[-1]) if not data["DX-Y.NYB"].empty else 0
        tnx_latest = float(data["^TNX"]["close"].iloc[-1]) if not data["^TNX"].empty else 0
        real_latest = float(data["FRED"]["dfii10"].iloc[-1]) if not data["FRED"].empty else 0
        gld_vol_latest = float(data["GLD"]["volume"].iloc[-1]) if not data["GLD"].empty else 0
        eur_latest = float(data["EURUSD=X"]["close"].iloc[-1]) if "EURUSD=X" in data and not data["EURUSD=X"].empty else 0
    except Exception:
        gold_latest = dxy_latest = tnx_latest = real_latest = gld_vol_latest = eur_latest = 0
    
    db.save_briefing(today, bias, gold_latest, dxy_latest, tnx_latest,
                     real_latest, gld_vol_latest, eur_latest, full_text)

# ─── ENTRY POINT ─────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--archive":
        archive_briefing()
    else:
        get_dual_macro_history()
