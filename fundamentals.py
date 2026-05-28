import yfinance as yf

def test_data_pull():
    print("--- ITERATION 1: PLUMBING TEST ---")
    try:
        dxy = yf.Ticker("DX-Y.NYB")
        current_dxy = dxy.history(period="1d")['Close'].iloc[-1]
        print(f"Success! The current US Dollar Index (DXY) is: {current_dxy:.2f}")
    except Exception as e:
        print(f"Error pulling data: {e}")

if __name__ == "__main__":
    test_data_pull()
