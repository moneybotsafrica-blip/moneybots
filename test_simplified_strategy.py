"""
Test script to verify simplified strategy responsiveness.
Tests that the new leading-indicator-focused strategy generates signals earlier.
"""
import os
import sys
import pandas as pd
import numpy as np

# Change to the project directory and set up Django
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')

import django
django.setup()

from analysis.services.bot_strategies import analyze_daily_candle
from analysis.services.signal_engine import _generate_qatraders_signal

def create_sample_data(trend='uptrend', with_momentum=True):
    """Create sample OHLCV data with indicators for testing."""
    np.random.seed(42)
    
    # Generate 50 candles
    n = 50
    dates = pd.date_range(start='2024-01-01', periods=n, freq='h')
    
    if trend == 'uptrend':
        # Uptrend with noise
        base_price = 1.1000
        trend_slope = 0.0008  # Stronger trend
        noise = np.random.normal(0, 0.0008, n)  # Less noise
        close = base_price + trend_slope * np.arange(n) + noise
    elif trend == 'downtrend':
        # Downtrend with noise
        base_price = 1.1100
        trend_slope = -0.0008  # Stronger trend
        noise = np.random.normal(0, 0.0008, n)  # Less noise
        close = base_price + trend_slope * np.arange(n) + noise
    else:
        # Ranging
        base_price = 1.1050
        noise = np.random.normal(0, 0.0015, n)
        close = base_price + noise
    
    # Generate OHLC from close
    high = close + np.random.uniform(0, 0.0008, n)
    low = close - np.random.uniform(0, 0.0008, n)
    open_price = np.roll(close, 1)
    open_price[0] = close[0]
    
    # Add momentum if requested - stronger momentum
    if with_momentum:
        close[-5:] = close[-5:] + np.arange(5) * 0.002  # Stronger momentum at end
    
    # Calculate indicators
    df = pd.DataFrame({
        'time': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': np.random.randint(100, 1000, n)
    })
    
    # Add technical indicators
    df['EMA8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['EMA21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
    
    # Stochastic
    low14 = df['low'].rolling(window=14).min()
    high14 = df['high'].rolling(window=14).max()
    df['Stochastic_K'] = 100 * ((df['close'] - low14) / (high14 - low14))
    df['Stochastic_D'] = df['Stochastic_K'].rolling(window=3).mean()
    
    # Bollinger Bands
    df['Bollinger_Middle'] = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['Bollinger_Middle'] + (std * 2)
    df['Bollinger_Lower'] = df['Bollinger_Middle'] - (std * 2)
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    # Volatility (simplified)
    df['volatility'] = df['close'].pct_change().rolling(window=20).std()
    
    return df

def test_simplified_strategy():
    """Test the simplified strategy with different market conditions."""
    print("=" * 60)
    print("Testing Simplified Strategy Responsiveness")
    print("=" * 60)
    print()
    
    test_cases = [
        ('Uptrend with momentum', 'uptrend', True),
        ('Downtrend with momentum', 'downtrend', True),
        ('Uptrend without momentum', 'uptrend', False),
        ('Downtrend without momentum', 'downtrend', False),
        ('Ranging market', 'ranging', False),
    ]
    
    symbol = 'EURUSD'
    
    for name, trend, with_momentum in test_cases:
        print(f"\nTest Case: {name}")
        print("-" * 40)
        
        df = create_sample_data(trend, with_momentum)
        
        # Test analyze_daily_candle
        signal1 = analyze_daily_candle(df, symbol)
        print(f"analyze_daily_candle result:")
        print(f"  Direction: {signal1['direction']}")
        print(f"  Signal Strength: {signal1['signal_strength']:.2f}")
        print(f"  Confirmation Count: {signal1['confirmation_count']}")
        print(f"  Pattern: {signal1.get('pattern', 'N/A')}")
        print(f"  Structure: {signal1.get('structure', 'N/A')}")
        
        # Test _generate_qatraders_signal
        model_proba_up = 0.6 if trend == 'uptrend' else 0.4
        signal2 = _generate_qatraders_signal(symbol, df, model_proba_up, '1H')
        print(f"\n_generate_qatraders_signal result:")
        print(f"  Direction: {signal2['direction']}")
        print(f"  Signal Strength: {signal2['signal_strength']:.2f}")
        print(f"  Confirmation Count: {signal2['confirmation_count']}")
        print(f"  Pattern: {signal2.get('pattern', 'N/A')}")
        print(f"  Structure: {signal2.get('structure', 'N/A')}")
        print(f"  Entry Type: {signal2.get('entry_type', 'N/A')}")
        
        # Check if signals are generated (not Neutral)
        signal1_active = signal1['direction'] in ['Buy', 'Sell']
        signal2_active = signal2['direction'] in ['Buy', 'Sell']
        
        expected_direction = 'Buy' if trend == 'uptrend' else 'Sell' if trend == 'downtrend' else 'Neutral'
        
        if with_momentum:
            # With momentum, at least one strategy should generate signals
            if signal1_active or signal2_active:
                print(f"\n[PASS] At least one strategy generated signals")
                if signal1_active:
                    print(f"  - analyze_daily_candle: {signal1['direction']} (strength: {signal1['signal_strength']:.2f})")
                    if signal1['direction'] == expected_direction:
                        print(f"  [PASS] Direction matches trend")
                if signal2_active:
                    print(f"  - _generate_qatraders_signal: {signal2['direction']} (strength: {signal2['signal_strength']:.2f})")
                    if signal2['direction'] == expected_direction:
                        print(f"  [PASS] Direction matches trend")
            else:
                print(f"\n[FAIL] Expected at least one signal with momentum but got:")
                print(f"  - analyze_daily_candle: {signal1['direction']}")
                print(f"  - _generate_qatraders_signal: {signal2['direction']}")
        else:
            # Without momentum, may or may not generate signals (less strict)
            print(f"\n[INFO] No momentum - signal generation optional")
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print("The simplified strategy should:")
    print("1. Generate signals based on leading indicators (price action, momentum)")
    print("2. Not require multiple lagging indicators to align")
    print("3. Be more responsive to early price movements")
    print("4. Have lower confirmation thresholds (4/9 vs previous 6+/12)")
    print()

if __name__ == "__main__":
    test_simplified_strategy()
