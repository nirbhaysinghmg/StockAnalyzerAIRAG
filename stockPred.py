import yfinance as yf
import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates

# Configure settings
pd.set_option('display.max_columns', None)
plt.style.use('seaborn-darkgrid')

# Indian stock tickers
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "KOTAKBANK.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "LT.NS", "MARUTI.NS", "ASIANPAINT.NS"
]

def fetch_stock_data(ticker, period='1y'):
    """Fetch historical stock data"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty:
            return None
        return df
    except:
        return None

def calculate_support_levels(df):
    """Calculate key support levels using multiple methods"""
    # Recent swing lows
    df['Swing_Low'] = df['Low'].rolling(window=20, center=True).min()
    
    # Moving averages (support levels)
    df['SMA_50'] = ta.sma(df['Close'], length=50)
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    
    # Fibonacci retracement levels
    max_price = df['High'].max()
    min_price = df['Low'].min()
    diff = max_price - min_price
    
    fib_levels = {
        'Fib_0.236': max_price - diff * 0.236,
        'Fib_0.382': max_price - diff * 0.382,
        'Fib_0.5': max_price - diff * 0.5,
        'Fib_0.618': max_price - diff * 0.618,
    }
    
    return df, fib_levels

def calculate_reversal_signals(df):
    """Calculate technical indicators for reversal signals"""
    # RSI for oversold conditions
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # MACD for momentum shifts
    macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    
    # Stochastic Oscillator
    stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3)
    df = pd.concat([df, stoch], axis=1)
    
    # Bollinger Bands
    bbands = ta.bbands(df['Close'], length=20)
    df = pd.concat([df, bbands], axis=1)
    
    # Volume analysis
    df['Volume_MA'] = df['Volume'].rolling(window=10).mean()
    
    return df

def detect_bullish_patterns(df):
    """Detect candlestick reversal patterns"""
    # Hammer pattern
    df['Hammer'] = (
        (df['Close'] > df['Open']) & 
        ((df['Close'] - df['Low']) > (1.5 * (df['High'] - df['Low']))) | (
        (df['Open'] > df['Close']) & 
        ((df['Open'] - df['Low']) > (1.5 * (df['High'] - df['Low'])))
    
    # Bullish Engulfing
    df['Bullish_Engulfing'] = (
        (df['Close'] > df['Open']) & 
        (df['Close'].shift(1) < df['Open'].shift(1)) & (
        (df['Close'] > df['Open'].shift(1)) & (
        (df['Open'] < df['Close'].shift(1))
    
    # Morning Star
    df['Morning_Star'] = (
        (df['Close'].shift(2) < df['Open'].shift(2)) & (
        (df['Close'].shift(1) < df['Open'].shift(1)) & (
        (df['Close'] > df['Open'])) & (
        (df['Close'] > (df['Open'].shift(2) + df['Close'].shift(2)) / 2)
    
    return df

def calculate_reversal_score(df, fib_levels):
    """Calculate a composite reversal score"""
    current_price = df['Close'].iloc[-1]
    
    # 1. Proximity to support levels
    support_distance = min([
        abs(current_price - df['Swing_Low'].iloc[-1]),
        abs(current_price - df['SMA_50'].iloc[-1]),
        abs(current_price - df['SMA_200'].iloc[-1]),
        min([abs(current_price - level) for level in fib_levels.values()])
    ])
    
    proximity_score = 1 - min(support_distance / current_price, 0.05) / 0.05
    
    # 2. Technical indicators score
    indicator_score = 0
    if df['RSI'].iloc[-1] < 35:
        indicator_score += 0.3
    if df['MACD_12_26_9'].iloc[-1] > df['MACDs_12_26_9'].iloc[-1]:
        indicator_score += 0.2
    if df['STOCHk_14_3_3'].iloc[-1] < 20:
        indicator_score += 0.2
    if df['Volume'].iloc[-1] > 1.5 * df['Volume_MA'].iloc[-1]:
        indicator_score += 0.3
    
    # 3. Bullish pattern score
    pattern_score = 0
    if df['Hammer'].iloc[-1]:
        pattern_score += 0.4
    if df['Bullish_Engulfing'].iloc[-1]:
        pattern_score += 0.6
    if df['Morning_Star'].iloc[-1]:
        pattern_score += 0.8
    
    # Composite score (0-10 scale)
    total_score = (proximity_score * 4) + (indicator_score * 3) + (pattern_score * 3)
    return min(total_score, 10)

def visualize_stock(ticker, df, fib_levels, score):
    """Create professional visualization for analysis"""
    plt.figure(figsize=(14, 10))
    
    # Price chart
    ax1 = plt.subplot(3, 1, 1)
    plt.plot(df['Close'], label='Price', color='royalblue', linewidth=2)
    plt.plot(df['SMA_50'], label='50 SMA', color='orange', linestyle='--')
    plt.plot(df['SMA_200'], label='200 SMA', color='purple', linestyle='-.')
    
    # Plot support levels
    plt.axhline(y=df['Swing_Low'].iloc[-1], color='green', linestyle='-', alpha=0.3, label='Swing Low')
    for name, level in fib_levels.items():
        plt.axhline(y=level, color='teal', linestyle=':', alpha=0.7, label=f'{name} Support')
    
    plt.title(f'{ticker} - Reversal Score: {score:.2f}/10', fontsize=16)
    plt.ylabel('Price', fontsize=12)
    plt.legend(loc='best')
    
    # Technical indicators
    ax2 = plt.subplot(3, 1, 2, sharex=ax1)
    plt.plot(df['RSI'], label='RSI', color='purple')
    plt.axhline(30, color='red', linestyle='--', alpha=0.3)
    plt.axhline(70, color='red', linestyle='--', alpha=0.3)
    plt.fill_between(df.index, 30, df['RSI'], where=(df['RSI']<30), color='green', alpha=0.3)
    plt.ylabel('RSI', fontsize=12)
    
    ax3 = ax2.twinx()
    plt.plot(df['MACD_12_26_9'], label='MACD', color='blue')
    plt.plot(df['MACDs_12_26_9'], label='Signal', color='red')
    plt.fill_between(df.index, 0, df['MACDh_12_26_9'], where=(df['MACDh_12_26_9']>0), color='green', alpha=0.3)
    plt.fill_between(df.index, 0, df['MACDh_12_26_9'], where=(df['MACDh_12_26_9']<0), color='red', alpha=0.3)
    plt.ylabel('MACD', fontsize=12)
    
    # Volume
    ax4 = plt.subplot(3, 1, 3, sharex=ax1)
    plt.bar(df.index, df['Volume'], color=np.where(df['Close'] > df['Open'], 'green', 'red'), alpha=0.8)
    plt.plot(df['Volume_MA'], color='blue', label='10D Avg Volume')
    plt.ylabel('Volume', fontsize=12)
    
    # Format dates
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b-%Y'))
    plt.gcf().autofmt_xdate()
    
    plt.tight_layout()
    plt.savefig(f"{ticker.replace('.', '_')}_analysis.png", dpi=300)
    plt.close()

def analyze_stocks():
    """Main function to analyze all stocks"""
    results = []
    
    for ticker in TICKERS:
        try:
            # Fetch data
            df = fetch_stock_data(ticker)
            if df is None or df.empty:
                continue
            
            # Calculate support levels
            df, fib_levels = calculate_support_levels(df)
            
            # Calculate reversal signals
            df = calculate_reversal_signals(df)
            df = detect_bullish_patterns(df)
            
            # Calculate reversal score
            score = calculate_reversal_score(df, fib_levels)
            
            # Only consider stocks with significant potential
            if score >= 6.0:
                # Generate visualization
                visualize_stock(ticker, df[-120:], fib_levels, score)
                
                # Add to results
                results.append({
                    'Ticker': ticker,
                    'Current Price': df['Close'].iloc[-1],
                    'Support Level': min(
                        df['Swing_Low'].iloc[-1],
                        df['SMA_50'].iloc[-1],
                        df['SMA_200'].iloc[-1],
                        min(fib_levels.values())
                    ),
                    'RSI': df['RSI'].iloc[-1],
                    'MACD': df['MACD_12_26_9'].iloc[-1],
                    'Reversal Score': score,
                    'Patterns': ', '.join([
                        p for p in ['Hammer', 'Bullish_Engulfing', 'Morning_Star'] 
                        if df[p].iloc[-1]
                    ])
                })
                
        except Exception as e:
            print(f"Error processing {ticker}: {str(e)}")
    
    # Create results DataFrame
    if results:
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('Reversal Score', ascending=False)
        results_df.to_csv('reversal_candidates.csv', index=False)
        
        print("\nTop Reversal Candidates:")
        print(results_df)
    else:
        print("No strong reversal candidates found")

if __name__ == "__main__":
    analyze_stocks()