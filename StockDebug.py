import yfinance as yf
import numpy as np
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta, time
import pytz

# Settings
IST = pytz.timezone('Asia/Kolkata')
TICKER = '^NSEI'
THRESHOLD = 2.0  # percent

# Get previous trading day (Mon-Fri)
def get_previous_trading_day():
    today = datetime.now(IST).date()
    prev_day = today - timedelta(days=1)
    if prev_day.weekday() == 6:  # Sunday
        prev_day = today - timedelta(days=2)
    elif prev_day.weekday() == 5:  # Saturday
        prev_day = today - timedelta(days=1)
    return prev_day

def make_utc(dt_date, hh, mm):
    return IST.localize(datetime.combine(dt_date, time(hh, mm))).astimezone(pytz.UTC)

def fetch_intraday_data(ticker, day):
    start_utc = make_utc(day, 9, 15)
    end_utc = make_utc(day, 15, 30)
    df = yf.download(
        ticker,
        start=start_utc,
        end=end_utc,
        interval='5m',
        progress=False
    )
    if df.empty:
        return None
    if df.index.tzinfo is None or df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert('Asia/Kolkata')
    return df

def calculate_intraday_supports(df):
    if df is None or df.empty or len(df) < 20:
        return None
    df = df.copy()
    df['Cumulative_TPV'] = ((df['High'] + df['Low'] + df['Close']) / 3) * df['Volume']
    df['Cumulative_V'] = df['Volume'].cumsum()
    df['VWAP'] = df['Cumulative_TPV'].cumsum() / df['Cumulative_V']
    df['SMA_20'] = ta.sma(df['Close'], length=20)
    df['SMA_50'] = ta.sma(df['Close'], length=50)
    supports = {
        'VWAP': df['VWAP'].iloc[-1],
        'SMA_20': df['SMA_20'].iloc[-1],
        'SMA_50': df['SMA_50'].iloc[-1],
        'Daily_Low': df['Low'].min(),
        'Daily_Close': df['Close'].iloc[-1]
    }
    return supports

def debug_nifty_support():
    prev_day = get_previous_trading_day()
    print(f"Debugging ^NSEI for {prev_day.strftime('%d-%b-%Y')}")
    df = fetch_intraday_data(TICKER, prev_day)
    if df is None or df.empty:
        print("No intraday data found for ^NSEI.")
        return
    supports = calculate_intraday_supports(df)
    if supports is None:
        print("Not enough data to calculate supports.")
        return
    close = supports['Daily_Close']
    if isinstance(close, pd.Series):
        close = close.iloc[-1]
    close = float(close)
    print(f"Close: {close:.2f}")
    found = False
    for name, level in supports.items():
        if name == 'Daily_Close' or level is None:
            continue
        if isinstance(level, pd.Series):
            level = level.iloc[-1]
        try:
            level = float(level)
        except Exception:
            continue
        if np.isnan(level):
            continue
        distance_pct = abs(close - level) / close * 100
        print(f"  {name}: {level:.2f} (Distance: {distance_pct:.2f}%)")
        if distance_pct <= THRESHOLD:
            print(f"    -> Close is within {THRESHOLD}% of {name} support!")
            found = True
    if not found:
        print(f"No support level within {THRESHOLD}% of close.")

if __name__ == "__main__":
    debug_nifty_support() 