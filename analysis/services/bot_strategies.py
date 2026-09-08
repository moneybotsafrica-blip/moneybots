"""
Trading strategies extracted from bot.py for integration into analysis signal generation.
Includes support/resistance detection, candlestick patterns, chart patterns, 
trend channel detection, and technical indicator scoring.
"""
import pandas as pd


def get_symbol_digits(symbol: str) -> int:
    """Return the number of decimal places for a given symbol."""
    if symbol.startswith("frx"):
        # Forex pairs: 5 decimal places (except JPY pairs which have 3)
        if "JPY" in symbol:
            return 3
        return 5
    elif symbol.startswith("R_") or symbol.startswith("1HZ"):
        # Volatility indices: 2 decimal places
        return 2
    elif any(x in symbol for x in ["BOOM", "CRASH", "Jump", "STPRD"]):
        # Synthetic indices: 2 decimal places
        return 2
    elif "XAU" in symbol or "GOLD" in symbol:
        # Gold: 2 decimal places
        return 2
    else:
        return 5


def round_to_symbol_digits(value: float, symbol: str) -> float:
    """Round a price value to the appropriate decimal places for MT5 compatibility."""
    digits = get_symbol_digits(symbol)
    return round(value, digits)

# NOTE: get_market_thresholds is imported lazily inside analyze_daily_candle
# (not at module scope) because signal_engine.py itself imports several
# names from this module — a top-level import here would be circular.


def detect_support_resistance(df, lookback=50):
    """Detect key support and resistance from swing highs/lows."""
    window = min(lookback, len(df) - 1)
    if window < 10:
        return {'support': [], 'resistance': []}

    recent = df.iloc[-window:]
    highs = recent['high'].values
    lows = recent['low'].values
    closes = recent['close'].values
    price = closes[-1]
    tolerance = price * 0.002

    resistance_levels = []
    support_levels = []

    for i in range(2, len(recent) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            resistance_levels.append(highs[i])
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            support_levels.append(lows[i])

    def cluster_levels(levels):
        if not levels:
            return []
        levels = sorted(levels)
        clustered = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - clustered[-1]) > tolerance:
                clustered.append(lvl)
        return clustered[-3:]

    return {
        'support': cluster_levels(support_levels),
        'resistance': cluster_levels(resistance_levels)
    }


def detect_candlestick_patterns(df):
    """Recognize common candlestick patterns on the last 3 candles."""
    patterns = []
    if len(df) < 3:
        return patterns

    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    body3 = abs(c3['close'] - c3['open'])
    range3 = c3['high'] - c3['low']
    upper_wick3 = c3['high'] - max(c3['open'], c3['close'])
    lower_wick3 = min(c3['open'], c3['close']) - c3['low']

    if range3 > 0 and body3 / range3 < 0.1:
        patterns.append(('Doji', 'neutral'))

    body2 = abs(c2['close'] - c2['open'])
    if body3 > body2 * 1.2:
        if c3['close'] > c3['open'] and c2['close'] < c2['open'] and c3['close'] > c2['open'] and c3['open'] < c2['close']:
            patterns.append(('Bullish Engulfing', 'bullish'))
        elif c3['close'] < c3['open'] and c2['close'] > c2['open'] and c3['close'] < c2['open'] and c3['open'] > c2['close']:
            patterns.append(('Bearish Engulfing', 'bearish'))

    if range3 > 0 and lower_wick3 > body3 * 2 and upper_wick3 < body3 * 0.5:
        patterns.append(('Hammer', 'bullish'))
    if range3 > 0 and upper_wick3 > body3 * 2 and lower_wick3 < body3 * 0.5:
        patterns.append(('Shooting Star', 'bearish'))

    if c1['close'] < c1['open'] and abs(c2['close'] - c2['open']) < body2 * 0.3 and c3['close'] > c3['open'] and c3['close'] > (c1['open'] + c1['close']) / 2:
        patterns.append(('Morning Star', 'bullish'))
    if c1['close'] > c1['open'] and abs(c2['close'] - c2['open']) < body2 * 0.3 and c3['close'] < c3['open'] and c3['close'] < (c1['open'] + c1['close']) / 2:
        patterns.append(('Evening Star', 'bearish'))

    return patterns


def detect_chart_patterns(df, lookback=60):
    """Identify chart patterns from recent price structure."""
    patterns = []
    window = min(lookback, len(df))
    if window < 20:
        return patterns

    recent = df.iloc[-window:]
    highs = recent['high'].values
    lows = recent['low'].values
    closes = recent['close'].values
    price = closes[-1]
    tolerance = price * 0.005

    def find_peaks(series):
        peaks = []
        for i in range(2, len(series) - 2):
            if series[i] > series[i - 1] and series[i] > series[i - 2] and series[i] > series[i + 1] and series[i] > series[i + 2]:
                peaks.append((i, series[i]))
        return peaks

    def find_troughs(series):
        troughs = []
        for i in range(2, len(series) - 2):
            if series[i] < series[i - 1] and series[i] < series[i - 2] and series[i] < series[i + 1] and series[i] < series[i + 2]:
                troughs.append((i, series[i]))
        return troughs

    peaks = find_peaks(highs)
    troughs = find_troughs(lows)

    # Detect Double Top/Bottom
    if len(peaks) >= 2:
        recent_peaks = peaks[-2:]
        if abs(recent_peaks[0][1] - recent_peaks[1][1]) < tolerance:
            if price < recent_peaks[0][1]:
                patterns.append(('Double Top', 'bearish'))

    if len(troughs) >= 2:
        recent_troughs = troughs[-2:]
        if abs(recent_troughs[0][1] - recent_troughs[1][1]) < tolerance:
            if price > recent_troughs[0][1]:
                patterns.append(('Double Bottom', 'bullish'))

    # Detect Head and Shoulders (simplified)
    if len(peaks) >= 3 and len(troughs) >= 2:
        recent_peaks = peaks[-3:]
        recent_troughs = troughs[-2:]
        if (recent_peaks[0][1] > recent_peaks[1][1] and 
            recent_peaks[2][1] > recent_peaks[1][1] and
            abs(recent_peaks[0][1] - recent_peaks[2][1]) < tolerance * 2):
            if price < recent_peaks[1][1]:
                patterns.append(('Head and Shoulders', 'bearish'))

    return patterns


def detect_trend_channel(df, lookback=30):
    """Identify trend direction and channel bounds."""
    window = min(lookback, len(df))
    if window < 10:
        return {'trend': 'Sideways', 'upper': None, 'lower': None}

    recent = df.iloc[-window:]
    def linear_fit(values):
        count = len(values)
        x_mean = (count - 1) / 2
        y_mean = sum(values) / count
        denominator = sum((index - x_mean) ** 2 for index in range(count))
        slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
        return slope, y_mean - slope * x_mean

    high_slope, high_intercept = linear_fit(recent['high'].tolist())
    low_slope, low_intercept = linear_fit(recent['low'].tolist())
    close_slope, _ = linear_fit(recent['close'].tolist())

    if close_slope > 0:
        trend = 'Uptrend'
    elif close_slope < 0:
        trend = 'Downtrend'
    else:
        trend = 'Sideways'

    return {
        'trend': trend,
        'upper': float(high_slope * (window - 1) + high_intercept),
        'lower': float(low_slope * (window - 1) + low_intercept)
    }


def score_technical_indicators(df):
    """Score RSI, MACD, Stochastic, Bollinger, and MA signals."""
    bullish, bearish, notes = 0, 0, []
    last = df.iloc[-1]
    prev = df.iloc[-2]

    rsi = float(last.get('RSI', 50))
    if rsi < 30:
        bullish += 2
        notes.append('RSI oversold (<30)')
    elif rsi > 70:
        bearish += 2
        notes.append('RSI overbought (>70)')
    elif rsi > 50:
        bullish += 1
        notes.append('RSI bullish momentum')
    else:
        bearish += 1
        notes.append('RSI bearish momentum')

    # RSI divergence (price vs RSI over last 10 bars)
    if len(df) >= 10:
        price_low_idx = df['close'].iloc[-10:].idxmin()
        price_high_idx = df['close'].iloc[-10:].idxmax()
        if df.loc[price_low_idx, 'close'] == df['close'].iloc[-10:].min() and last['close'] > df.loc[price_low_idx, 'close'] and rsi < float(df.loc[price_low_idx, 'RSI']):
            bullish += 2
            notes.append('RSI bullish divergence')
        if df.loc[price_high_idx, 'close'] == df['close'].iloc[-10:].max() and last['close'] < df.loc[price_high_idx, 'close'] and rsi > float(df.loc[price_high_idx, 'RSI']):
            bearish += 2
            notes.append('RSI bearish divergence')

    macd = float(last.get('MACD', 0))
    macd_sig = float(last.get('MACD_Signal', 0))
    macd_hist = float(last.get('MACD_Histogram', 0))
    prev_hist = float(prev.get('MACD_Histogram', 0))

    if macd > macd_sig and prev_hist <= 0 < macd_hist:
        bullish += 2
        notes.append('MACD bullish crossover')
    elif macd < macd_sig and prev_hist >= 0 > macd_hist:
        bearish += 2
        notes.append('MACD bearish crossover')
    elif macd_hist > 0:
        bullish += 1
        notes.append('MACD histogram positive')
    elif macd_hist < 0:
        bearish += 1
        notes.append('MACD histogram negative')

    if macd_hist > prev_hist:
        bullish += 1
    elif macd_hist < prev_hist:
        bearish += 1

    stoch_k = float(last.get('Stochastic_K', 50))
    stoch_d = float(last.get('Stochastic_D', 50))
    prev_k = float(prev.get('Stochastic_K', 50))
    prev_d = float(prev.get('Stochastic_D', 50))

    if stoch_k < 20 and stoch_d < 20:
        bullish += 1
        notes.append('Stochastic oversold')
    elif stoch_k > 80 and stoch_d > 80:
        bearish += 1
        notes.append('Stochastic overbought')
    if prev_k <= prev_d and stoch_k > stoch_d:
        bullish += 1
        notes.append('Stochastic K/D bullish cross')
    elif prev_k >= prev_d and stoch_k < stoch_d:
        bearish += 1
        notes.append('Stochastic K/D bearish cross')

    bb_upper = float(last.get('Bollinger_Upper', last['close']))
    bb_lower = float(last.get('Bollinger_Lower', last['close']))
    bb_mid = float(last.get('Bollinger_Middle', last['close']))

    if last['close'] < bb_lower:
        bullish += 1
        notes.append('Price below lower BB')
    elif last['close'] > bb_upper:
        bearish += 1
        notes.append('Price above upper BB')

    ema8 = float(last.get('EMA8', last['close']))
    ema21 = float(last.get('EMA21', last['close']))

    if last['close'] > ema8 and ema8 > ema21:
        bullish += 1
        notes.append('Price above EMAs (uptrend)')
    elif last['close'] < ema8 and ema8 < ema21:
        bearish += 1
        notes.append('Price below EMAs (downtrend)')

    return bullish, bearish, notes


def analyze_daily_candle(df, symbol):
    """
    Simplified strategy focused on leading indicators and price action.
    Reduces confirmation bias by removing excessive lagging indicators.
    Focuses on: price action patterns, momentum, and simple trend direction.
    """
    try:
        if len(df) < 20:
            return {'direction': 'Neutral', 'signal_strength': 0}

        last = df.iloc[-1]
        atr = float(last.get('ATR', 0))
        if atr <= 0:
            return {'direction': 'Neutral', 'signal_strength': 0}

        close = float(last['close'])
        
        # Focus on leading indicators: price action patterns and momentum
        candle_patterns = detect_candlestick_patterns(df)
        sr_levels = detect_support_resistance(df)
        
        # Simple momentum check (price change over last 5 bars)
        price_momentum = (close - df['close'].iloc[-5]) / df['close'].iloc[-5] if len(df) >= 5 else 0
        
        # Simple trend direction using single EMA (not multiple alignment)
        ema21 = float(last.get('EMA21', close))
        simple_trend = 'Uptrend' if close > ema21 else 'Downtrend'
        
        # RSI for extreme conditions only (not ranges)
        rsi = float(last.get('RSI', 50))
        
        # Score based on leading indicators only
        bullish_score = 0
        bearish_score = 0
        all_patterns = []
        
        # Candlestick patterns (leading - price action)
        for name, bias in candle_patterns:
            all_patterns.append(name)
            if bias == 'bullish':
                bullish_score += 3
            elif bias == 'bearish':
                bearish_score += 3
        
        # Price momentum (leading)
        if price_momentum > 0.002:  # Strong upward momentum
            bullish_score += 2
        elif price_momentum < -0.002:  # Strong downward momentum
            bearish_score += 2
        
        # Support/Resistance proximity (leading - price at key levels)
        if sr_levels['support']:
            nearest_support = min(sr_levels['support'], key=lambda x: abs(x - close))
            if abs(close - nearest_support) / close < 0.005:  # Near support
                bullish_score += 2
        if sr_levels['resistance']:
            nearest_resistance = min(sr_levels['resistance'], key=lambda x: abs(x - close))
            if abs(close - nearest_resistance) / close < 0.005:  # Near resistance
                bearish_score += 2
        
        # Simple trend alignment (not multiple EMAs)
        if simple_trend == 'Uptrend':
            bullish_score += 1
        else:
            bearish_score += 1
        
        # RSI extreme only (not ranges - reduces lag)
        if rsi < 30:  # Oversold
            bullish_score += 2
        elif rsi > 70:  # Overbought
            bearish_score += 2
        
        net_score = bullish_score - bearish_score
        total_confirmations = max(bullish_score, bearish_score)
        
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': '',
            'structure': simple_trend,
            'confirmation_count': 0,
            'patterns_identified': all_patterns,
            'support_resistance': sr_levels,
            'technical_notes': [],
            'ema8': float(last.get('EMA8', close)),
            'ema21': ema21,
            'rsi': rsi,
            'macd_hist': float(last.get('MACD_Histogram', 0)),
            'atr': atr,
            'avg_atr': float(df['ATR'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else atr,
        }
        
        # Simplified threshold: need net score of 1+ (very low) and only 20% strength
        from markets.catalog import get_market_type
        from .signal_engine import get_market_thresholds
        
        max_possible_score = 8  # Reduced from 12
        strength = min(abs(net_score) / max_possible_score, 1.0)
        
        # Very low threshold for earliest entries (0.2 instead of 0.4)
        min_strength = 0.2
        
        if net_score >= 1 and strength >= min_strength:
            signal['direction'] = 'Buy'
            signal['confirmation_count'] = total_confirmations
        elif net_score <= -1 and strength >= min_strength:
            signal['direction'] = 'Sell'
            signal['confirmation_count'] = total_confirmations
        else:
            return signal
        
        signal['signal_strength'] = strength
        signal['confirmations'] = all_patterns
        
        # Risk-reward based on strength
        if signal['signal_strength'] >= 0.6:
            signal['risk_reward'] = 2.5
        else:
            signal['risk_reward'] = 1.5
        
        # Tighter stops for earlier entries
        sl_distance = atr * 1.2  # Reduced from 1.5
        if signal['direction'] == 'Buy':
            signal['entry'] = close
            signal['stop_loss'] = round_to_symbol_digits(close - sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(close + sl_distance * signal['risk_reward'], symbol)
        else:
            signal['entry'] = close
            signal['stop_loss'] = round_to_symbol_digits(close + sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(close - sl_distance * signal['risk_reward'], symbol)
        
        primary_pattern = all_patterns[0] if all_patterns else f"{simple_trend} + Momentum"
        signal['pattern'] = primary_pattern
        
        return signal

    except Exception as e:
        import logging
        logging.error(f"Error in analyze_daily_candle: {e}")
        return {'direction': 'Neutral', 'signal_strength': 0}
