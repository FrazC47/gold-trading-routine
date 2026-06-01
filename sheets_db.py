"""
sheets_db.py — Google Sheets persistence layer for fundamentals.py
Uses Sheet ID directly for unambiguous access.
"""

import os
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import requests
import io

# ─── CONFIG ──────────────────────────────────────────────────────────
# Your GoldTracker workbook ID (from the URL)
SHEET_ID = "1aJLVlqbpe4tzLRIozKTyajBchyj2CfGyo0mBCqRJwcE"
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS", "credentials.json")

TICKER_CONFIG = {
    "GC=F":     {"sheet": "GC=F",    "cols": ["date","open","high","low","close","volume"]},
    "DX-Y.NYB": {"sheet": "DXY",     "cols": ["date","open","high","low","close"]},
    "^TNX":     {"sheet": "TNX",     "cols": ["date","open","high","low","close"]},
    "GLD":      {"sheet": "GLD",     "cols": ["date","open","high","low","close","volume"]},
    "EURUSD=X": {"sheet": "EURUSD",  "cols": ["date","open","high","low","close"]},
}

# ─── AUTH ────────────────────────────────────────────────────────────
def _get_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds)

def _get_workbook():
    """Open workbook by ID — unambiguous, no name collision risk."""
    return _get_client().open_by_key(SHEET_ID)

# ─── READ SHEET ──────────────────────────────────────────────────────
def _read_sheet(sheet_name):
    try:
        wb = _get_workbook()
        ws = wb.worksheet(sheet_name)
        return ws.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        return []
    except Exception as e:
        print(f"    [sheets_db] Warning reading {sheet_name}: {e}")
        return []

# ─── APPEND ROW ──────────────────────────────────────────────────────
def _append_row(sheet_name, row):
    try:
        wb = _get_workbook()
        ws = wb.worksheet(sheet_name)
        ws.append_row(row)
        time.sleep(0.5)
    except Exception as e:
        print(f"    [sheets_db] Warning writing to {sheet_name}: {e}")

# ─── SYNC ONE TICKER ─────────────────────────────────────────────────
def sync_ticker(ticker):
    config = TICKER_CONFIG[ticker]
    sheet = config["sheet"]
    records = _read_sheet(sheet)
    
    if not records:
        print(f"    [sheets_db] {ticker}: cold start — fetching 30 days from yfinance...")
        df_yf = yf.download(ticker, period="30d", interval="1d", progress=False)
        if df_yf.empty:
            return pd.DataFrame(columns=config["cols"])
        df_yf = df_yf.reset_index()
        if isinstance(df_yf.columns, pd.MultiIndex):
            df_yf.columns = df_yf.columns.get_level_values(0)
        df_yf.columns = [c.lower().replace(' ', '_') for c in df_yf.columns]
        df_yf["date"] = pd.to_datetime(df_yf["date"]).dt.date

        for _, row in df_yf.iterrows():
            r = [str(row["date"]), row["open"], row["high"], row["low"], row["close"]]
            if "volume" in config["cols"]:
                r.append(int(row["volume"]))
            _append_row(sheet, r)
        return df_yf[config["cols"]]
    
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    latest = df["date"].max()
    today = datetime.now().date()
    
    days_missing = (today - latest).days
    if days_missing <= 1:
        print(f"    [sheets_db] {ticker}: current through {latest}")
        return df[config["cols"]]
    
    start = (latest + timedelta(days=1)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"    [sheets_db] {ticker}: filling gap {start} → {end}")
    
    df_yf = yf.download(ticker, start=start, end=end, interval="1d", progress=False)
    if df_yf.empty:
        print(f"    [sheets_db] {ticker}: no new data available")
        return df[config["cols"]]
    
    df_yf = df_yf.reset_index()
    if isinstance(df_yf.columns, pd.MultiIndex):
        df_yf.columns = df_yf.columns.get_level_values(0)
    df_yf.columns = [c.lower().replace(' ', '_') for c in df_yf.columns]
    df_yf["date"] = pd.to_datetime(df_yf["date"]).dt.date

    appended = 0
    for _, row in df_yf.iterrows():
        if row["date"] > latest:
            r = [str(row["date"]), row["open"], row["high"], row["low"], row["close"]]
            if "volume" in config["cols"]:
                r.append(int(row["volume"]))
            _append_row(sheet, r)
            appended += 1
    
    print(f"    [sheets_db] {ticker}: synced {appended} new rows")
    return df[config["cols"]]

# ─── SYNC FRED ───────────────────────────────────────────────────────
def sync_fred():
    records = _read_sheet("FRED")
    
    if not records:
        print("    [sheets_db] FRED: cold start — fetching from FRED...")
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
        df = pd.read_csv(url)
        df.columns = ["date", "dfii10"]
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[df["date"] >= (datetime.now().date() - timedelta(days=30))]
        df = df.dropna()
        for _, row in df.iterrows():
            _append_row("FRED", [str(row["date"]), row["dfii10"]])
        return df
    
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    latest = df["date"].max()
    today = datetime.now().date()
    
    if (today - latest).days <= 2:
        print(f"    [sheets_db] FRED: current through {latest}")
        return df
    
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
    df_fresh = pd.read_csv(url)
    df_fresh.columns = ["date", "dfii10"]
    df_fresh["date"] = pd.to_datetime(df_fresh["date"]).dt.date
    df_fresh = df_fresh[df_fresh["date"] > latest].dropna()
    
    for _, row in df_fresh.iterrows():
        _append_row("FRED", [str(row["date"]), row["dfii10"]])
    
    print(f"    [sheets_db] FRED: synced {len(df_fresh)} new rows")
    return df

# ─── SYNC ALL ────────────────────────────────────────────────────────
def sync_all():
    print("[STEP 1] Syncing with Google Sheets...")
    results = {}
    
    for ticker in TICKER_CONFIG.keys():
        df = sync_ticker(ticker)
        if not df.empty:
            results[ticker] = df
    
    results["FRED"] = sync_fred()
    print("✅ Sync complete. Data ready.\n")
    return results

# ─── SAVE BRIEFING ───────────────────────────────────────────────────
def save_briefing(date_str, bias, gold, dxy, nominal_yield, real_yield,
                  gld_volume, eurusd, full_text):
    try:
        wb = _get_workbook()
        try:
            ws = wb.worksheet("Briefings")
        except gspread.exceptions.WorksheetNotFound:
            ws = wb.add_worksheet("Briefings", rows=1000, cols=10)
            ws.append_row(["date","bias","gold","dxy","nominal_yield",
                          "real_yield","gld_volume","eurusd","text"])
        
        ws.append_row([
            date_str, bias, gold, dxy, nominal_yield,
            real_yield, gld_volume, eurusd, full_text[:4500]
        ])
        print(f"\n✅ Briefing archived to GoldTracker/Briefings.")
    except Exception as e:
        print(f"\n⚠️ Archive failed: {e}")
