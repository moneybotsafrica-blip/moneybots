"""
Technical indicator functions — ported from bot.py's
calculate_rsi / calculate_macd / calculate_bollinger_bands / calculate_atr /
calculate_stochastic_oscillator / add_technical_indicators.

Kept as pure pandas so the analysis engine has no dependency on the `ta`
package (one less thing to install on the Pi/host).
"""
import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(series: pd.Series, short_window=12, long_window=26, signal_window=9) -> pd.Series:
    short_ema = series.ewm(span=short_window, adjust=False).mean()
    long_ema = series.ewm(span=long_window, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_window, adjust=False).mean()
    return macd - signal


def calculate_bollinger_bands(series: pd.Series, window=20, num_sd=2):
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_sd)
    lower_band = rolling_mean - (rolling_std * num_sd)
    return upper_band, lower_band


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_stochastic_oscillator(high: pd.Series, low: pd.Series, close: pd.Series, period=14):
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=3).mean()
    return k, d


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds the full indicator set the ML pipeline and signal engine expect.
    Enhanced with additional indicators from the advanced trading strategy.
    """
    df = df.copy()
    
    # Core indicators (always calculated)
    df["SMA_20"] = df["close"].rolling(window=20).mean()
    df["EMA_12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["close"])
    df["MACD"] = calculate_macd(df["close"])
    df["Bollinger_Upper"], df["Bollinger_Lower"] = calculate_bollinger_bands(df["close"])
    df["Momentum"] = df["close"].diff(4)
    df["EMA_26"] = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD_Histogram"] = df["MACD"] - df["EMA_26"]
    df["Stochastic_K"], df["Stochastic_D"] = calculate_stochastic_oscillator(
        df["high"], df["low"], df["close"], period=14
    )
    df["mean"] = df["close"].rolling(window=20).mean()
    df["median"] = df["close"].rolling(window=20).median()
    df["std"] = df["close"].rolling(window=20).std()
    df["ATR"] = calculate_atr(df)

    df["returns"] = df["close"].pct_change()
    df["volatility"] = df["returns"].rolling(window=20).std()

    # Fast EMAs used by the signal engine for quick entries (CRITICAL)
    df["EMA5"] = df["close"].ewm(span=5, adjust=False).mean()
    df["EMA8"] = df["close"].ewm(span=8, adjust=False).mean()
    df["EMA10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["EMA13"] = df["close"].ewm(span=13, adjust=False).mean()
    df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["EMA21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["EMA30"] = df["close"].ewm(span=30, adjust=False).mean()
    df["EMA50"] = df["close"].ewm(span=50, adjust=False).mean()
    
    # Additional indicators for advanced strategies
    # MACD Signal line
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    
    # ADX indicator (simplified version)
    try:
        # Calculate True Range
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Calculate +DM and -DM
        df["+DM"] = df["high"].diff()
        df["+DM"] = df["+DM"].where((df["+DM"] > 0) & (df["high"].diff() > df["low"].diff()), 0)
        df["-DM"] = df["low"].diff()
        df["-DM"] = df["-DM"].where((df["-DM"] > 0) & (df["low"].diff() > df["high"].diff()), 0)
        df["-DM"] = df["-DM"].abs()
        
        # Calculate smoothed values
        period = 14
        atr_smooth = tr.rolling(window=period).mean()
        plus_dm_smooth = df["+DM"].rolling(window=period).mean()
        minus_dm_smooth = df["-DM"].rolling(window=period).mean()
        
        # Calculate +DI and -DI
        df["+DI"] = 100 * (plus_dm_smooth / atr_smooth)
        df["-DI"] = 100 * (minus_dm_smooth / atr_smooth)
        
        # Calculate DX and ADX
        df["DX"] = 100 * abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])
        df["ADX"] = df["DX"].rolling(window=period).mean()
        
        # Clean up temporary columns
        df.drop(["+DM", "-DM", "+DI", "-DI", "DX"], axis=1, inplace=True)
    except Exception:
        # If ADX calculation fails, set default value
        df["ADX"] = 20  # Default moderate trend strength
    
    # Bollinger Band Middle and Width for regime detection
    df["BB_Middle"] = df["close"].rolling(window=20).mean()
    df["BB_Std"] = df["close"].rolling(window=20).std()
    df["BB_Upper"] = df["BB_Middle"] + (2 * df["BB_Std"])
    df["BB_Lower"] = df["BB_Middle"] - (2 * df["BB_Std"])
    df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Middle"]
    
    # 20-bar high/low for breakout strategy
    df["High_20"] = df["high"].rolling(window=20).max()
    df["Low_20"] = df["low"].rolling(window=20).min()
    
    # ATR 20-bar average for volatility comparison
    df["ATR_20"] = df["ATR"].rolling(window=20).mean()

    # Additional indicators for enhanced signal generation
    df["EMA_Separation"] = abs(df["EMA8"] - df["EMA21"])
    df["ATR_Ratio"] = df["ATR"] / df["ATR"].rolling(20).mean()
    
    # Enhanced ML features for better accuracy (optional, may fail with insufficient data)
    try:
        df["Price_Change_5"] = df["close"].pct_change(5)
        df["Price_Change_10"] = df["close"].pct_change(10)
        df["High_Low_Ratio"] = df["high"] / df["low"]
        df["Upper_Shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / (df["high"] - df["low"])
        df["Lower_Shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / (df["high"] - df["low"])
        df["Body_Size"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"])
        
        # Trend strength indicators
        df["EMA_Slope_8"] = df["EMA8"].diff()
        df["EMA_Slope_21"] = df["EMA21"].diff()
        df["Trend_Strength"] = abs(df["EMA_Slope_8"]) / df["ATR"]
        
        # RSI divergence detection
        df["RSI_Divergence"] = df["RSI"].diff()
        df["Price_RSI_Ratio"] = df["close"].pct_change() / (df["RSI"].pct_change() + 0.001)
        
        # Bollinger Band position
        df["BB_Position"] = (df["close"] - df["Bollinger_Lower"]) / (df["Bollinger_Upper"] - df["Bollinger_Lower"])
        df["BB_Width"] = (df["Bollinger_Upper"] - df["Bollinger_Lower"]) / df["close"]
        
        # Stochastic momentum
        df["Stochastic_Momentum"] = df["Stochastic_K"].diff()
    except Exception:
        # If enhanced features fail, continue without them
        pass
    
    # Volume proxy (price-based since volume not available from Deriv)
    df["Volume_SMA"] = df["close"].rolling(window=7).mean()

    # Only drop NaN values for core indicators, keep optional features even if NaN
    core_columns = ["open", "high", "low", "close", "volatility", "SMA_20", "RSI", "MACD",
                    "Bollinger_Upper", "Bollinger_Lower", "Momentum", "ATR", "EMA_12",
                    "EMA_26", "MACD_Histogram", "Stochastic_K", "Stochastic_D",
                    "mean", "median", "std", "EMA8", "EMA21", "EMA10", "EMA20", "EMA30", "EMA50",
                    "MACD_Signal", "ADX", "BB_Middle", "BB_Width", "High_20", "Low_20", "ATR_20"]
    
    df.dropna(subset=core_columns, inplace=True)
    return df


NUMERIC_FEATURES = [
    "open", "high", "low", "close", "volatility", "SMA_20", "RSI", "MACD",
    "Bollinger_Upper", "Bollinger_Lower", "Momentum", "ATR", "EMA_12",
    "EMA_26", "MACD_Histogram", "Stochastic_K", "Stochastic_D",
    "mean", "median", "std",
    # Enhanced ML features (optional - may not always be available)
    "Price_Change_5", "Price_Change_10", "High_Low_Ratio",
    "Upper_Shadow", "Lower_Shadow", "Body_Size",
    "EMA_Slope_8", "EMA_Slope_21", "Trend_Strength",
    "RSI_Divergence", "Price_RSI_Ratio",
    "BB_Position", "BB_Width", "Stochastic_Momentum",
]
