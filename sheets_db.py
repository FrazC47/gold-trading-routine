"""
sheets_db.py — Google Sheets persistence layer for fundamentals.py
Uses Sheet ID directly for unambiguous access.
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import requests
import io

# ─── CONFIG ──────────────────────────────────────────────────────────
SHEET_ID = "1aJLVlqbpe4tzLRIozKTyajBchyj2CfGyo0mBCqRJwcE"
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS", "credentials.json")

TICKER_CONFIG = {
    "GC=F":     {"sheet": "GC=F",    "cols": ["date","open","high","low","close","volume"]},
    "DX-Y.NYB": {"sheet": "DXY",     "cols": ["date","open","high","low","close"]},
    "^TNX":     {"sheet": "TNX",     "cols": ["date","open","high","low","close"]},
    "GLD":      {"sheet": "GLD",     "cols": ["date","open","high","low","close","volume"]},
    "EURUSD=X": {"sheet": "EURUSD",  "cols": ["date","open","high","low","close"]},
}

# ─── AUTH — cached for the lifetime of the process ───────────────────
_workbook_cache = None

def _get_workbook():
    """Return a cached workbook handle; open once per process run."""
    global _workbook_cache
    if _workbook_cache is None:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        _workbook_cache = client.open_by_key(SHEET_ID)
    return _workbook_cache

# ─── READ SHEET ──────────────────────────────────────────────────────
def _read_sheet(sheet_name, expected_cols):
    """Read a sheet and return a list of dicts with expected_cols as keys.

    Uses get_all_values() (raw rows) so behaviour is deterministic regardless
    of whether the sheet already has a proper header row or was populated
    without one (header row detection based on first-row equality).
    """
    try:
        ws = _get_workbook().worksheet(sheet_name)
        values = ws.get_all_values()
        if not values:
            return []
        # Strip all cell values (Google Sheets can return trailing spaces).
        values = [[str(c).strip() for c in row] for row in values]
        # Skip first row if it matches the expected header; otherwise treat all rows as data.
        data_rows = values[1:] if values[0] == expected_cols else values
        n = len(expected_cols)
        first_col = expected_cols[0]  # e.g. "date"
        records = []
        for row in data_rows:
            if not any(row):
                continue
            # Skip any stray header rows (e.g. duplicated by failed clear+append retries)
            if row[0] == first_col:
                continue
            # Pad short rows so zip always produces a full dict
            padded = list(row) + [""] * (n - len(row))
            records.append(dict(zip(expected_cols, padded[:n])))
        return records
    except gspread.exceptions.WorksheetNotFound:
        return []
    except Exception as e:
        print(f"    [sheets_db] Warning reading {sheet_name}: {e}")
        return []

# ─── BATCH WRITE ─────────────────────────────────────────────────────
def _append_rows_batch(sheet_name, rows):
    """Append all rows in a single API call instead of one call per row."""
    if not rows:
        return
    try:
        ws = _get_workbook().worksheet(sheet_name)
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"    [sheets_db] Warning writing to {sheet_name}: {e}")

# ─── PARSE YFINANCE DATAFRAME ─────────────────────────────────────────
def _parse_yf(df_yf):
    df_yf = df_yf.reset_index()
    if isinstance(df_yf.columns, pd.MultiIndex):
        df_yf.columns = df_yf.columns.get_level_values(0)
    df_yf.columns = [c.lower().replace(' ', '_') for c in df_yf.columns]
    df_yf["date"] = pd.to_datetime(df_yf["date"]).dt.date
    return df_yf

def _build_rows(df_yf, has_volume):
    rows = []
    for _, row in df_yf.iterrows():
        r = [str(row["date"]),
             float(row["open"]), float(row["high"]),
             float(row["low"]),  float(row["close"])]
        if has_volume:
            r.append(int(row["volume"]))
        rows.append(r)
    return rows

# ─── SYNC ONE TICKER ─────────────────────────────────────────────────
def sync_ticker(ticker):
    config = TICKER_CONFIG[ticker]
    sheet = config["sheet"]
    cols = config["cols"]
    has_volume = "volume" in cols
    records = _read_sheet(sheet, cols)

    if not records:
        print(f"    [sheets_db] {ticker}: cold start — fetching 30 days from yfinance...")
        df_yf = yf.download(ticker, period="30d", interval="1d", progress=False)
        if df_yf.empty:
            return pd.DataFrame(columns=cols)
        df_yf = _parse_yf(df_yf)
        # Clear any stale/corrupt rows before writing so we never get duplicate headers
        try:
            _get_workbook().worksheet(sheet).clear()
        except gspread.exceptions.WorksheetNotFound:
            pass
        _append_rows_batch(sheet, [cols] + _build_rows(df_yf, has_volume))
        return df_yf[cols]

    df = pd.DataFrame(records)
    for col in cols:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    latest = df["date"].max()
    today = datetime.now().date()

    if (today - latest).days <= 1:
        print(f"    [sheets_db] {ticker}: current through {latest}")
        return df[cols]

    start = (latest + timedelta(days=1)).strftime("%Y-%m-%d")
    end   = (today  + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"    [sheets_db] {ticker}: filling gap {start} → {end}")

    df_yf = yf.download(ticker, start=start, end=end, interval="1d", progress=False)
    if df_yf.empty:
        print(f"    [sheets_db] {ticker}: no new data available")
        return df[cols]

    df_yf = _parse_yf(df_yf)
    df_new = df_yf[df_yf["date"] > latest]
    new_rows = _build_rows(df_new, has_volume)
    _append_rows_batch(sheet, new_rows)
    print(f"    [sheets_db] {ticker}: synced {len(new_rows)} new rows")
    # Return merged dataset so caller has the full up-to-date range in memory
    return pd.concat([df[cols], df_new[cols]], ignore_index=True)

# ─── SYNC FRED ───────────────────────────────────────────────────────
FRED_COLS = ["date", "dfii10"]

def sync_fred():
    records = _read_sheet("FRED", FRED_COLS)

    if not records:
        print("    [sheets_db] FRED: cold start — fetching from FRED...")
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
        df = pd.read_csv(url)
        df.columns = FRED_COLS
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[df["date"] >= (datetime.now().date() - timedelta(days=30))].dropna()
        try:
            _get_workbook().worksheet("FRED").clear()
        except gspread.exceptions.WorksheetNotFound:
            pass
        _append_rows_batch("FRED", [FRED_COLS] + [[str(r["date"]), r["dfii10"]] for _, r in df.iterrows()])
        return df

    df = pd.DataFrame(records)
    df["dfii10"] = pd.to_numeric(df["dfii10"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    latest = df["date"].max()
    today = datetime.now().date()

    if (today - latest).days <= 2:
        print(f"    [sheets_db] FRED: current through {latest}")
        return df

    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
    df_fresh = pd.read_csv(url)
    df_fresh.columns = FRED_COLS
    df_fresh["date"] = pd.to_datetime(df_fresh["date"]).dt.date
    df_fresh = df_fresh[df_fresh["date"] > latest].dropna()
    _append_rows_batch("FRED", [[str(r["date"]), r["dfii10"]] for _, r in df_fresh.iterrows()])
    print(f"    [sheets_db] FRED: synced {len(df_fresh)} new rows")
    return pd.concat([df, df_fresh[FRED_COLS]], ignore_index=True)

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
