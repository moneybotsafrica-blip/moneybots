"""
Signal scoring — ported from bot.py's generate_trade_signals(),
calculate_scalp_opportunity(), get_market_thresholds(), get_entry_type(),
get_risk_level(), and the SL/TP/R:R sizing constants from the top of the
file. MT5 order-placement pieces are intentionally left out — this only
ever produces a Signal dict for display / paper-position sizing.
"""
from __future__ import annotations

import pandas as pd

from analysis.services.bot_strategies import (
    analyze_daily_candle,
    detect_candlestick_patterns,
    detect_chart_patterns,
    detect_support_resistance,
    detect_trend_channel,
    score_technical_indicators,
)
from markets.catalog import display_name, get_market_type

# TRADER PLATFORM-style constants for day trading & scalping
SL_ATR_BASE = 1.0  # Tighter stops for scalping
SL_ATR_STRENGTH_FACTOR = 0.3
RR_BASE = 2.0  # Higher R:R for better risk management
RR_STRENGTH_FACTOR = 0.5
MIN_RISK_REWARD = 1.2  # Minimum R:R requirement
MIN_SIGNAL_STRENGTH = 0.35  # Lower threshold for more signals
MIN_CONFIRMATIONS = 1  # Minimum confirmations required
MAX_VOLATILITY_MULTIPLIER = 2.0  # More permissive volatility filter


def get_symbol_digits(symbol: str) -> int:
    """Return the number of decimal places for a symbol (MT5 compatible)."""
    # Forex pairs typically have 5 decimal places (3 for JPY pairs)
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 3
        return 5
    # Commodities have 2 decimal places
    if "XAU" in symbol or "XAG" in symbol or "WTI" in symbol or "NG" in symbol:
        return 2
    # Synthetic indices have 5 decimal places
    if symbol.startswith("BOOM") or symbol.startswith("CRASH") or symbol.startswith("Jump"):
        return 5
    # Volatility indices have 5 decimal places
    if symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 5
    # Default to 5 decimal places
    return 5


def get_symbol_points(symbol: str) -> float:
    """Return the point value for a symbol (MT5 minimum distance unit)."""
    digits = get_symbol_digits(symbol)
    return 10 ** (-digits)


def get_minimum_distance(symbol: str) -> float:
    """
    Return minimum distance for TP/SL from current price (MT5 requirement).
    MT5 has symbol-specific minimum distances to prevent invalid orders.
    """
    points = get_symbol_points(symbol)
    
    # Minimum distances in points (symbol-specific)
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 10 * points  # 10 pips for JPY pairs
        return 5 * points  # 5 pips for other forex
    elif "XAU" in symbol:
        return 20 * points  # 20 points for gold
    elif "XAG" in symbol:
        return 10 * points  # 10 points for silver
    elif symbol.startswith("BOOM") or symbol.startswith("CRASH"):
        return 50 * points  # Higher minimum for synthetic
    elif symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 10 * points  # 10 points for volatility
    else:
        return 5 * points  # Default minimum


def round_to_symbol_digits(value: float, symbol: str) -> float:
    """Round a price value to the appropriate decimal places for MT5 compatibility."""
    digits = get_symbol_digits(symbol)
    return round(value, digits)


def get_market_thresholds(market_type: str) -> dict:
    # Updated thresholds for more aggressive signal generation (matching standalone script)
    if market_type in ("forex", "commodities"):
        return {"early_entry": 0.55, "full_entry": 0.65}  # Lower thresholds for more signals
    if market_type == "synthetic":
        return {"early_entry": 0.60, "full_entry": 0.70}  # Moderate thresholds
    return {"early_entry": 0.65, "full_entry": 0.75}  # volatility


def get_entry_type(opportunity_score_pct: float, confirmation_strength: float = 0) -> str:
    """
    Determine entry type based on signals (from qatraders).
    confirmation_strength is optional for backward compatibility.
    """
    score = opportunity_score_pct / 100.0 if opportunity_score_pct > 1 else opportunity_score_pct
    if score >= 0.8:
        return "Strong Trend Entry"
    if score >= 0.7:
        return "Confirmed Entry"
    if score >= 0.6:
        return "Early Entry"
    return "Potential Setup"


def get_risk_level(current_atr: float, avg_atr: float) -> str:
    if not avg_atr:
        return "normal"
    ratio = current_atr / avg_atr
    if ratio > 1.5:
        return "high"
    if ratio < 0.8:
        return "low"
    return "normal"


def detect_market_condition(df: pd.DataFrame) -> str:
    """
    Detect if market is trending or ranging using ADX and EMA slope.
    Returns 'trending' or 'ranging'.
    """
    if len(df) < 50:
        return 'ranging'
    
    try:
        # Calculate ADX-like trend strength using price range
        high = df['high'].rolling(14).max()
        low = df['low'].rolling(14).min()
        tr = (high - low).rolling(14).mean()
        atr = df['ATR'].rolling(14).mean()
        
        if tr.empty or atr.empty:
            return 'ranging'
        
        # Trend strength ratio - ensure scalar values
        tr_val = float(tr.iloc[-1]) if len(tr) > 0 else 0
        atr_val = float(atr.iloc[-1]) if len(atr) > 0 else 0.0001
        trend_strength = tr_val / atr_val if atr_val > 0 else 0
        
        # EMA slope analysis - ensure scalar values
        ema8_slope = float(df['EMA8'].iloc[-1]) - float(df['EMA8'].iloc[-5])
        ema21_slope = float(df['EMA21'].iloc[-1]) - float(df['EMA21'].iloc[-5])
        
        # Strong trend if EMA slopes are consistent and trend strength is high
        if trend_strength > 1.2 and abs(ema8_slope) > 0 and abs(ema21_slope) > 0:
            if (ema8_slope > 0 and ema21_slope > 0) or (ema8_slope < 0 and ema21_slope < 0):
                return 'trending'
    except Exception:
        # If any calculation fails, default to ranging
        return 'ranging'
    
    return 'ranging'


def get_adaptive_confirmations(market_condition: str, volatility_ratio: float) -> int:
    """
    Return adaptive confirmation threshold based on market conditions.
    Trending markets require fewer confirmations, ranging markets require more.
    """
    if market_condition == 'trending':
        # Trending markets: fewer confirmations needed
        if volatility_ratio > 1.3:
            return 5  # High volatility trending: moderate confirmations
        return 4  # Normal trending: fewer confirmations
    else:
        # Ranging markets: more confirmations needed for accuracy
        if volatility_ratio > 1.3:
            return 7  # High volatility ranging: maximum confirmations
        return 6  # Normal ranging: more confirmations


def analyze_multi_timeframe_confluence(df: pd.DataFrame, direction: str) -> dict:
    """
    Simplified multi-timeframe analysis - less restrictive to reduce confirmation bias.
    Only checks short and medium term, not long term (reduces lag).
    """
    if len(df) < 50:
        return {"score": 1, "alignment": ["Insufficient data - assumed aligned"], "details": "Default alignment"}
    
    confluence_score = 0
    alignment_details = []
    
    # Short-term trend (last 10 candles) - leading
    short_term_ema = df['EMA8'].iloc[-10:].mean()
    short_term_price = df['close'].iloc[-10:].mean()
    short_trend = "bullish" if short_term_price > short_term_ema else "bearish"
    
    # Medium-term trend (last 30 candles) - less lagging than long-term
    medium_term_ema = df['EMA21'].iloc[-30:].mean()
    medium_term_price = df['close'].iloc[-30:].mean()
    medium_trend = "bullish" if medium_term_price > medium_term_ema else "bearish"
    
    # Check alignment with signal direction
    if direction == "Buy":
        if short_trend == "bullish":
            confluence_score += 1
            alignment_details.append("Short-term bullish")
        if medium_trend == "bullish":
            confluence_score += 1
            alignment_details.append("Medium-term bullish")
    else:  # Sell
        if short_trend == "bearish":
            confluence_score += 1
            alignment_details.append("Short-term bearish")
        if medium_trend == "bearish":
            confluence_score += 1
            alignment_details.append("Medium-term bearish")
    
    # Less restrictive: allow 1/2 alignment (was requiring 2/2 or 3/3)
    if confluence_score >= 1:
        return {
            "score": confluence_score,
            "alignment": alignment_details,
            "details": f"{confluence_score}/2 timeframes aligned"
        }
    
    # Even if no alignment, don't block - just note it
    return {
        "score": 1,  # Minimum score to not block
        "alignment": ["No MTF alignment - proceeding anyway"],
        "details": "MTF optional"
    }


def check_higher_timeframe_signal(symbol: str, current_timeframe: str) -> dict:
    """
    Simplified higher timeframe check - made optional to reduce confirmation bias.
    Only checks one higher timeframe instead of multiple, and doesn't block if not aligned.
    """
    from analysis.services.deriv_client import feed
    
    # Simplified hierarchy - only check one higher timeframe
    timeframe_hierarchy = {
        '1M': ['5M'],
        '5M': ['15M'],
        '15M': ['1H'],
        '1H': ['4H'],
        '4H': ['1D'],
        '1D': []  # No higher timeframe
    }
    
    higher_timeframes = timeframe_hierarchy.get(current_timeframe, [])
    
    if not higher_timeframes:
        return {"aligned": True, "details": "No higher timeframe to check"}
    
    # Get current dataframe
    df_current = feed.get_dataframe(symbol)
    if df_current is None or len(df_current) < 50:
        return {"aligned": True, "details": "Insufficient data - HTF optional"}
    
    # Check if required indicators exist
    if 'EMA8' not in df_current.columns or 'EMA21' not in df_current.columns:
        return {"aligned": True, "details": "HTF indicators not ready - HTF optional"}
    
    # Determine current signal direction from current timeframe
    current_ema8 = df_current['EMA8'].iloc[-1]
    current_ema21 = df_current['EMA21'].iloc[-1]
    current_direction = "Buy" if current_ema8 > current_ema21 else "Sell"
    
    # Simplified lookback periods
    lookback_periods = {
        '5M': 12,
        '15M': 36,
        '1H': 60,
        '4H': 240,
        '1D': 1440
    }
    
    htf = higher_timeframes[0]  # Only check first (closest) higher timeframe
    lookback = lookback_periods.get(htf, 60)
    
    if len(df_current) < lookback:
        return {"aligned": True, "details": f"Insufficient data for {htf} - HTF optional"}
    
    # Simulate higher timeframe trend
    htf_df = df_current.iloc[-lookback:]
    if 'EMA8' not in htf_df.columns or 'EMA21' not in htf_df.columns:
        return {"aligned": True, "details": f"{htf} indicators not ready - HTF optional"}
        
    htf_ema8 = htf_df['EMA8'].iloc[-1]
    htf_ema21 = htf_df['EMA21'].iloc[-1]
    htf_direction = "Buy" if htf_ema8 > htf_ema21 else "Sell"
    
    # Don't block if not aligned - just note it
    is_aligned = htf_direction == current_direction
    
    return {
        "aligned": True,  # Always return True to not block
        "current_direction": current_direction,
        "htf_direction": htf_direction,
        "details": f"{htf} {'aligned' if is_aligned else 'misaligned'} - HTF optional"
    }


def calculate_scalp_opportunity(signal_strength, rsi, volatility, atr, volume_confirm, market_type) -> float:
    """
    Calculate opportunity score optimized for scalping (from qatraders strategy).
    """
    base_score = signal_strength * 100
    
    # Scalping modifiers - wider RSI range for more opportunities
    if 40 <= rsi <= 60:  # Ideal RSI range for scalping
        base_score *= 1.2
    elif 35 <= rsi <= 65:  # Acceptable range
        base_score *= 1.0
    else:  # Outside ideal range
        base_score *= 0.7
        
    # Volatility check
    vol_avg = volatility * 100
    if vol_avg < 1.0:  # Low volatility
        base_score *= 1.2
    elif vol_avg < 1.5:  # Medium volatility
        base_score *= 1.0
    else:  # High volatility
        base_score *= 0.6
        
    # Volume confirmation
    if volume_confirm:
        base_score *= 1.2
    else:
        base_score *= 0.7
        
    # Market type considerations
    if market_type == 'synthetic':
        base_score *= 0.95
    elif market_type == 'volatility':
        base_score *= 0.9
        
    return min(base_score, 100)


def generate_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Enhanced signal generation using qatraders strategy.
    Uses weighted conditions, fast EMAs, and more aggressive entry criteria.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = float(current.get("RSI", 50))
    atr = float(current.get("ATR", 0)) or 0.0001
    volatility = float(current.get("volatility", 0) or 0)
    market_type = get_market_type(symbol)
    avg_atr = float(df["ATR"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else atr
    current_price = float(current['close'])
    
    # Pre-filters for quality
    if atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "High volatility filter")
    
    # Use qatraders weighted condition approach
    base_signal = _generate_qatraders_signal(symbol, df, model_proba_up, timeframe)
    
    # Apply additional quality filters
    if base_signal['direction'] not in ['Buy', 'Sell']:
        return base_signal
    
    # Calculate enhanced SL/TP with MT5 precision
    strength = base_signal['signal_strength']
    sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.0)
    rr = RR_BASE + RR_STRENGTH_FACTOR * strength
    sl_distance = atr * sl_atr_mult
    tp_distance = sl_distance * rr
    
    if base_signal['direction'] == 'Buy':
        base_signal['stop_loss'] = round_to_symbol_digits(current_price - sl_distance, symbol)
        base_signal['take_profit'] = round_to_symbol_digits(current_price + tp_distance, symbol)
    else:
        base_signal['stop_loss'] = round_to_symbol_digits(current_price + sl_distance, symbol)
        base_signal['take_profit'] = round_to_symbol_digits(current_price - tp_distance, symbol)
    
    base_signal['risk_reward'] = round(rr, 2)
    
    # Ensure minimum R:R
    if base_signal['risk_reward'] < MIN_RISK_REWARD:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                     f"Below R:R threshold ({base_signal['risk_reward']:.1f} < {MIN_RISK_REWARD})")
    
    # Complete signal with all required fields
    base_signal['symbol'] = symbol
    base_signal['market_name'] = display_name(symbol)
    base_signal['market_type'] = market_type
    base_signal['price'] = current_price
    base_signal['rsi'] = rsi
    base_signal['atr'] = atr
    base_signal['risk_level'] = get_risk_level(atr, avg_atr)
    
    # Volume confirmation (use ATR as proxy)
    volume_confirm = atr > avg_atr * 0.8
    base_signal['opportunity_score'] = calculate_scalp_opportunity(strength, rsi, volatility, atr, volume_confirm, market_type)
    base_signal['setup_quality'] = strength * 100
    base_signal['entry_type'] = get_entry_type(base_signal['opportunity_score'])
    base_signal['model_confidence'] = model_proba_up if base_signal['direction'] == 'Buy' else 1.0 - model_proba_up
    
    return base_signal


def _create_neutral_signal(symbol: str, market_type: str, current, rsi: float, atr: float, reason: str) -> dict:
    """Create a neutral signal with filter reason."""
    return {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": "Neutral",
        "signal_strength": 0.0,
        "setup_quality": 0.0,
        "entry_type": "",
        "confirmation_count": 0,
        "price": float(current['close']),
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, atr),
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "opportunity_score": 0.0,
        "structure": "Neutral",
        "pattern": f"Filter: {reason}",
    }


def _generate_qatraders_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Simplified signal generation focused on leading indicators.
    Removes excessive lagging indicators and multi-timeframe confirmations.
    Focuses on: price action, simple momentum, and RSI extremes.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]

    # Ensure all values are scalars
    def safe_float(value, default=0.0):
        """Convert value to float, handling pandas Series and arrays."""
        if isinstance(value, pd.Series):
            return float(value.iloc[-1])
        return float(value) if pd.notna(value) else default

    rsi = safe_float(current.get("RSI"), 50)
    current_price = safe_float(current["close"])
    current_high = safe_float(current["high"])
    current_low = safe_float(current["low"])
    prev_high = safe_float(prev["high"])
    prev_low = safe_float(prev["low"])

    # Simple EMA for trend direction (not multiple alignment)
    ema8 = safe_float(df['close'].ewm(span=8, adjust=False).mean().iloc[-1], current_price)

    atr = safe_float(current.get("ATR"), 0.0001)
    avg_atr = safe_float(df["ATR"].rolling(20).mean().iloc[-1], atr) if len(df) >= 20 else atr
    volatility = safe_float(current.get("volatility"), 0)

    market_type = get_market_type(symbol)

    # Initialize signal
    signal = {
        'direction': 'Neutral',
        'signal_strength': 0,
        'entry_type': '',
        'confirmation_count': 0,
        'setup_quality': 0,
        'pattern': '',
        'structure': '',
        'timeframe': timeframe,
    }

    # Simplified conditions - focus on leading indicators only
    # Price momentum (leading)
    price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5] if len(df) >= 5 else 0
    
    # Candlestick direction (leading - price action)
    bullish_candle = current_price > current["open"]
    bearish_candle = current_price < current["open"]
    
    # Higher low / lower high (price action)
    higher_low = current_low >= prev_low * 0.9995
    lower_high = current_high <= prev_high * 1.0005
    
    # Simple trend (not multiple EMAs)
    uptrend = current_price > ema8
    downtrend = current_price < ema8
    
    # RSI extremes only (not ranges - reduces lag)
    rsi_oversold = rsi < 30
    rsi_overbought = rsi > 70

    # Score based on leading indicators
    long_score = 0
    short_score = 0
    
    # Long conditions (leading indicators)
    if bullish_candle:
        long_score += 2  # Price action
    if higher_low:
        long_score += 2  # Price structure
    if uptrend:
        long_score += 1  # Simple trend
    if price_momentum > 0.002:
        long_score += 2  # Strong momentum
    if rsi_oversold:
        long_score += 2  # Extreme condition (leading signal)
    
    # Short conditions (leading indicators)
    if bearish_candle:
        short_score += 2  # Price action
    if lower_high:
        short_score += 2  # Price structure
    if downtrend:
        short_score += 1  # Simple trend
    if price_momentum < -0.002:
        short_score += 2  # Strong momentum
    if rsi_overbought:
        short_score += 2  # Extreme condition (leading signal)

    # Simplified threshold: need 4+ points (out of 9 max)
    min_score = 4

    # More sensitive prediction threshold
    if model_proba_up > 0.45 and long_score >= min_score:
        signal['direction'] = 'Buy'
        signal['signal_strength'] = min(long_score / 9.0, 1.0)
        signal['entry_type'] = 'Aggressive' if long_score >= 6 else 'Standard'
        signal['confirmation_count'] = long_score
        signal['setup_quality'] = (long_score / 9.0) * 100
        signal['structure'] = 'Uptrend' if uptrend else 'Downtrend'
        
        # Build pattern description from leading indicators
        confirmations = []
        if bullish_candle:
            confirmations.append('Bullish candle')
        if higher_low:
            confirmations.append('Higher low')
        if price_momentum > 0.002:
            confirmations.append('Strong momentum')
        if rsi_oversold:
            confirmations.append('RSI oversold')
        signal['pattern'] = ', '.join(confirmations[:3])
        
    elif model_proba_up < 0.55 and short_score >= min_score:
        signal['direction'] = 'Sell'
        signal['signal_strength'] = min(short_score / 9.0, 1.0)
        signal['entry_type'] = 'Aggressive' if short_score >= 6 else 'Standard'
        signal['confirmation_count'] = short_score
        signal['setup_quality'] = (short_score / 9.0) * 100
        signal['structure'] = 'Downtrend' if downtrend else 'Uptrend'
        
        # Build pattern description from leading indicators
        confirmations = []
        if bearish_candle:
            confirmations.append('Bearish candle')
        if lower_high:
            confirmations.append('Lower high')
        if price_momentum < -0.002:
            confirmations.append('Strong momentum')
        if rsi_overbought:
            confirmations.append('RSI overbought')
        signal['pattern'] = ', '.join(confirmations[:3])

    # Add additional fields
    signal['symbol'] = symbol
    signal['market_name'] = display_name(symbol)
    signal['market_type'] = market_type
    signal['price'] = current_price
    signal['rsi'] = rsi
    signal['atr'] = atr
    signal['risk_level'] = get_risk_level(atr, avg_atr)
    signal['stop_loss'] = None
    signal['take_profit'] = None
    signal['risk_reward'] = None
    signal['opportunity_score'] = 0.0

    return signal


def _generate_enhanced_ml_signal(symbol: str, df: pd.DataFrame, model_proba_up: float, timeframe: str = "1H") -> dict:
    """
    Enhanced ML-based signal generation with adaptive confirmations.
    Uses market condition detection to adjust confirmation requirements.
    """
    current = df.iloc[-1]
    prev = df.iloc[-2]

    # Ensure all values are scalars to avoid array ambiguity errors
    def safe_float(value, default=0.0):
        """Convert value to float, handling pandas Series and arrays."""
        if isinstance(value, pd.Series):
            return float(value.iloc[-1])
        return float(value) if pd.notna(value) else default

    rsi = safe_float(current.get("RSI"), 50)
    macd_hist = safe_float(current.get("MACD_Histogram"), 0)
    prev_macd_hist = safe_float(prev.get("MACD_Histogram"), 0)

    stoch_k = safe_float(current.get("Stochastic_K"), 50)
    stoch_d = safe_float(current.get("Stochastic_D"), 50)
    prev_stoch_k = safe_float(prev.get("Stochastic_K"), 50)

    current_price = safe_float(current["close"])
    current_high = safe_float(current["high"])
    current_low = safe_float(current["low"])
    prev_high = safe_float(prev["high"])
    prev_low = safe_float(prev["low"])

    ema8 = safe_float(current.get("EMA8"), current_price)
    ema21 = safe_float(current.get("EMA21"), current_price)
    ema50 = safe_float(current.get("EMA50"), ema21) if "EMA50" in current else ema21  # Fallback to EMA21 if EMA50 not available
    ema_sep = abs(ema8 - ema21)

    atr = safe_float(current.get("ATR"), 0.0001)
    avg_atr = safe_float(df["ATR"].rolling(20).mean().iloc[-1], atr) if len(df) >= 20 else atr
    volatility = safe_float(current.get("volatility"), 0)
    volatility_ratio = atr / avg_atr if avg_atr > 0 else 1.0

    market_type = get_market_type(symbol)
    
    # Detect market condition for adaptive thresholds
    market_condition = detect_market_condition(df)
    adaptive_confirmations = get_adaptive_confirmations(market_condition, volatility_ratio)

    # Enhanced volatility filter
    if avg_atr and atr > 0 and atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "High volatility filter")

    # Minimum EMA separation (stricter)
    min_sep = 0.20 * atr
    if ema_sep < min_sep:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "Insufficient EMA separation")

    # Trend structure
    structure = "Uptrend" if ema8 > ema21 else "Downtrend"

    # Enhanced 9-factor confirmation system
    trend_strength = 0
    confirmations = []

    # 1. EMA alignment (8 vs 21)
    if ema8 > ema21:
        trend_strength += 1
        confirmations.append("EMA bullish (8>21)")
        direction = "Buy"
    elif ema8 < ema21:
        trend_strength += 1
        confirmations.append("EMA bearish (8<21)")
        direction = "Sell"
    else:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "EMA crossover unclear")

    # 2. RSI zone - TRADER PLATFORM style (allow reversion or momentum)
    if direction == "Buy" and (rsi <= 35 or (50 <= rsi <= 62)):
        trend_strength += 1
        confirmations.append("RSI bullish" if rsi <= 35 else "RSI momentum")
    elif direction == "Sell" and (rsi >= 65 or (38 <= rsi <= 50)):
        trend_strength += 1
        confirmations.append("RSI bearish" if rsi >= 65 else "RSI momentum")

    # 3. MACD momentum - TRADER PLATFORM style
    if direction == "Buy" and macd_hist > 0 and macd_hist > prev_macd_hist:
        trend_strength += 1
        confirmations.append("MACD bullish")
    elif direction == "Sell" and macd_hist < 0 and macd_hist < prev_macd_hist:
        trend_strength += 1
        confirmations.append("MACD bearish")

    # 4. Candlestick direction - TRADER PLATFORM style
    if direction == "Buy" and current_price > current["open"]:
        trend_strength += 1
        confirmations.append("Bullish candle")
    elif direction == "Sell" and current_price < current["open"]:
        trend_strength += 1
        confirmations.append("Bearish candle")

    # 5. Price vs EMA8 - TRADER PLATFORM style
    if direction == "Buy" and current_price > ema8:
        trend_strength += 1
        confirmations.append("Price above EMA8")
    elif direction == "Sell" and current_price < ema8:
        trend_strength += 1
        confirmations.append("Price below EMA8")

    n_factors = 5  # TRADER PLATFORM 5-factor system

    # Use adaptive confirmation threshold based on market conditions
    if trend_strength < MIN_CONFIRMATIONS:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr,
                                     f"Insufficient confirmations ({trend_strength}/{MIN_CONFIRMATIONS})")

    signal = {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": direction,
        "signal_strength": trend_strength / float(n_factors),
        "setup_quality": (trend_strength / n_factors) * 100,
        "entry_type": "",
        "confirmation_count": trend_strength,
        "price": current_price,
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, avg_atr),
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "opportunity_score": 0.0,
        "structure": structure,
        "pattern": f"Bot (RSI, EMA, MACD, 5-factor): {', '.join(confirmations[:3])}",
        "timeframe": timeframe,
        "htf_advice": "",
    }

    # Set entry type based on strength - TRADER PLATFORM style
    if trend_strength >= 4:
        signal["entry_type"] = "Strong " + ("Bullish" if direction == "Buy" else "Bearish")
    elif trend_strength >= 3:
        signal["entry_type"] = "Confirmed " + ("Bullish" if direction == "Buy" else "Bearish")
    else:
        signal["entry_type"] = "Weak " + ("Bullish" if direction == "Buy" else "Bearish")

    # Volume confirmation (use ATR as proxy)
    volume_confirm = atr > avg_atr * 0.8
    signal["opportunity_score"] = calculate_scalp_opportunity(
        signal["signal_strength"], rsi, volatility, atr, volume_confirm, market_type
    )

    # Calculate SL/TP with enhanced parameters and MT5 validation
    strength = signal["signal_strength"]
    sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.0)
    rr = RR_BASE + RR_STRENGTH_FACTOR * strength
    sl_distance = atr * sl_atr_mult
    tp_distance = sl_distance * rr

    # Get MT5 minimum distance requirements
    min_distance = get_minimum_distance(symbol)
    points = get_symbol_points(symbol)

    # Ensure SL/TP meet minimum distance requirements
    sl_distance = max(sl_distance, min_distance)
    tp_distance = max(tp_distance, min_distance * MIN_RISK_REWARD)

    # Calculate raw SL/TP
    if signal["direction"] == "Buy":
        raw_sl = current_price - sl_distance
        raw_tp = current_price + tp_distance
    else:
        raw_sl = current_price + sl_distance
        raw_tp = current_price - tp_distance

    # Round to symbol digits and ensure minimum distance
    signal["stop_loss"] = round_to_symbol_digits(raw_sl, symbol)
    signal["take_profit"] = round_to_symbol_digits(raw_tp, symbol)

    # Final validation: ensure minimum distance after rounding
    if signal["direction"] == "Buy":
        sl_dist_final = current_price - signal["stop_loss"]
        tp_dist_final = signal["take_profit"] - current_price
    else:
        sl_dist_final = signal["stop_loss"] - current_price
        tp_dist_final = current_price - signal["take_profit"]

    # If rounding reduced distance below minimum, adjust
    if sl_dist_final < min_distance:
        adjustment = (min_distance - sl_dist_final)
        if signal["direction"] == "Buy":
            signal["stop_loss"] = round_to_symbol_digits(signal["stop_loss"] - adjustment, symbol)
        else:
            signal["stop_loss"] = round_to_symbol_digits(signal["stop_loss"] + adjustment, symbol)

    if tp_dist_final < min_distance * MIN_RISK_REWARD:
        adjustment = (min_distance * MIN_RISK_REWARD - tp_dist_final)
        if signal["direction"] == "Buy":
            signal["take_profit"] = round_to_symbol_digits(signal["take_profit"] + adjustment, symbol)
        else:
            signal["take_profit"] = round_to_symbol_digits(signal["take_profit"] - adjustment, symbol)

    signal["risk_reward"] = round(rr, 2)

    return signal


def passes_trade_filters(signal: dict) -> bool:
    """
    TRADER PLATFORM-style trade filters for day trading & scalping.
    More permissive to allow more signals for scalping opportunities.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return False
    if signal["signal_strength"] < MIN_SIGNAL_STRENGTH:
        return False
    if not signal.get("risk_reward") or signal["risk_reward"] < MIN_RISK_REWARD:
        return False
    if signal.get("confirmation_count", 0) < MIN_CONFIRMATIONS:
        return False
    
    # Basic quality checks
    if not signal.get("stop_loss") or not signal.get("take_profit"):
        return False
    
    # Ensure SL/TP are reasonable distances from entry
    current_price = signal.get("price", 0)
    sl_distance = abs(current_price - signal["stop_loss"])
    tp_distance = abs(signal["take_profit"] - current_price)
    
    if sl_distance <= 0 or tp_distance <= 0:
        return False
    
    # TP should be at least MIN_RISK_REWARD times SL
    if tp_distance < sl_distance * MIN_RISK_REWARD:
        return False
    
    # TRADER PLATFORM: No HTF check, no setup quality check, no RSI extreme check
    # More permissive for scalping opportunities
    
    thresholds = get_market_thresholds(signal["market_type"])
    return signal["signal_strength"] >= thresholds["early_entry"]


def get_mt5_signal_format(signal: dict) -> dict:
    """
    Convert internal signal format to MT5-compatible format.
    Includes all fields needed for MT5 order execution.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return None
    
    mt5_action = 0  # TRADE_ACTION_DEAL
    mt5_type = 0 if signal["direction"] == "Buy" else 1  # 0=BUY, 1=SELL
    
    return {
        "action": mt5_action,
        "symbol": signal["symbol"],
        "volume": 0.01,  # Default lot size, should be calculated based on risk
        "type": mt5_type,
        "price": signal["price"],
        "sl": signal["stop_loss"],
        "tp": signal["take_profit"],
        "deviation": 20,  # Max price deviation in points
        "magic": 123456,  # EA magic number
        "comment": f"AI Signal {signal.get('entry_type', 'Manual')}",
        "type_time": 0,  # ORDER_TIME_GTC
        "type_filling": 0,  # ORDER_FILLING_IOC
    }


def calculate_position_size(signal: dict, account_balance: float, risk_percent: float = 1.0) -> float:
    """
    Calculate optimal position size based on risk management.
    Uses ATR-based SL to determine lot size for given risk percentage.
    """
    if signal["direction"] not in ("Buy", "Sell"):
        return 0.01  # Minimum lot size
    
    current_price = signal.get("price", 0)
    sl_price = signal.get("stop_loss")
    
    if not sl_price or current_price <= 0:
        return 0.01
    
    # Calculate SL distance in price units
    sl_distance = abs(current_price - sl_price)
    
    # Calculate risk amount in account currency
    risk_amount = account_balance * (risk_percent / 100.0)
    
    # Calculate position size (simplified - MT5 would need more precise calculation)
    # This is a basic calculation - real implementation would need symbol-specific pip values
    if sl_distance > 0:
        position_size = risk_amount / sl_distance
        # Round to standard lot sizes (0.01, 0.1, 1.0, etc.)
        position_size = max(0.01, min(position_size, 100.0))  # Cap at 100 lots
        position_size = round(position_size, 2)
        # Ensure minimum lot size
        position_size = max(0.01, position_size)
    else:
        position_size = 0.01
    
    return position_size
