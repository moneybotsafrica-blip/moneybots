"""
Enhanced ML-based signal generation with technical indicators.
Uses leading indicators and adaptive confirmations for reliable signals.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

from markets.catalog import display_name, get_market_type, all_symbols
from analysis.services.indicators import add_technical_indicators

# Signal generation parameters
SL_ATR_BASE = 1.0
SL_ATR_STRENGTH_FACTOR = 0.3
RR_BASE = 2.0
RR_STRENGTH_FACTOR = 0.5
MIN_RISK_REWARD = 1.2
MIN_SIGNAL_STRENGTH = 0.35
MIN_CONFIRMATIONS = 1
MAX_VOLATILITY_MULTIPLIER = 2.0

# Higher timeframe configuration
PRIMARY_TIMEFRAME = "H1"
HIGHER_TIMEFRAME_ENABLED = True


def get_symbol_digits(symbol: str) -> int:
    """Return the number of decimal places for a symbol."""
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 3
        return 5
    if "XAU" in symbol or "XAG" in symbol or "WTI" in symbol or "NG" in symbol:
        return 2
    if symbol.startswith("BOOM") or symbol.startswith("CRASH") or symbol.startswith("Jump"):
        return 5
    if symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 5
    return 5


def get_symbol_points(symbol: str) -> float:
    """Return the point value for a symbol."""
    digits = get_symbol_digits(symbol)
    return 10 ** (-digits)


def get_minimum_distance(symbol: str) -> float:
    """Return minimum distance for TP/SL from current price."""
    points = get_symbol_points(symbol)
    
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 10 * points
        return 5 * points
    elif "XAU" in symbol:
        return 20 * points
    elif "XAG" in symbol:
        return 10 * points
    elif symbol.startswith("BOOM") or symbol.startswith("CRASH"):
        return 50 * points
    elif symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 10 * points
    else:
        return 5 * points


def round_to_symbol_digits(value: float, symbol: str) -> float:
    """Round a price value to the appropriate decimal places."""
    digits = get_symbol_digits(symbol)
    return round(value, digits)


def get_market_thresholds(market_type: str) -> dict:
    """Get market-specific signal thresholds."""
    if market_type in ("forex", "commodities"):
        return {"early_entry": 0.55, "full_entry": 0.65}
    if market_type == "synthetic":
        return {"early_entry": 0.60, "full_entry": 0.70}
    return {"early_entry": 0.65, "full_entry": 0.75}


def get_entry_type(opportunity_score_pct: float, confirmation_strength: float = 0) -> str:
    """Determine entry type based on signals."""
    score = opportunity_score_pct / 100.0 if opportunity_score_pct > 1 else opportunity_score_pct
    if score >= 0.8:
        return "Strong Trend Entry"
    if score >= 0.7:
        return "Confirmed Entry"
    if score >= 0.6:
        return "Early Entry"
    return "Potential Setup"


def get_risk_level(current_atr: float, avg_atr: float) -> str:
    """Determine risk level based on ATR."""
    if not avg_atr:
        return "normal"
    ratio = current_atr / avg_atr
    if ratio > 1.5:
        return "high"
    if ratio < 0.8:
        return "low"
    return "normal"


def detect_market_condition(df: pd.DataFrame) -> str:
    """Detect if market is trending or ranging."""
    if len(df) < 50:
        return 'ranging'
    
    try:
        high = df['high'].rolling(14).max()
        low = df['low'].rolling(14).min()
        tr = (high - low).rolling(14).mean()
        atr = df['ATR'].rolling(14).mean()
        
        if tr.empty or atr.empty:
            return 'ranging'
        
        tr_val = float(tr.iloc[-1]) if len(tr) > 0 else 0
        atr_val = float(atr.iloc[-1]) if len(atr) > 0 else 0.0001
        trend_strength = tr_val / atr_val if atr_val > 0 else 0
        
        ema8_slope = float(df['EMA8'].iloc[-1]) - float(df['EMA8'].iloc[-5])
        ema21_slope = float(df['EMA21'].iloc[-1]) - float(df['EMA21'].iloc[-5])
        
        if trend_strength > 1.2 and abs(ema8_slope) > 0 and abs(ema21_slope) > 0:
            if (ema8_slope > 0 and ema21_slope > 0) or (ema8_slope < 0 and ema21_slope < 0):
                return 'trending'
    except Exception:
        return 'ranging'
    
    return 'ranging'


def calculate_scalp_opportunity(signal_strength, rsi, volatility, atr, volume_confirm, market_type) -> float:
    """Calculate opportunity score optimized for scalping."""
    base_score = signal_strength * 100
    
    if 40 <= rsi <= 60:
        base_score *= 1.2
    elif 35 <= rsi <= 65:
        base_score *= 1.0
    else:
        base_score *= 0.7
        
    vol_avg = volatility * 100
    if vol_avg < 1.0:
        base_score *= 1.2
    elif vol_avg < 1.5:
        base_score *= 1.0
    else:
        base_score *= 0.6
        
    if volume_confirm:
        base_score *= 1.2
    else:
        base_score *= 0.7
        
    if market_type == 'synthetic':
        base_score *= 0.95
    elif market_type == 'volatility':
        base_score *= 0.9
        
    return min(base_score, 100)


def generate_ml_signal(symbol: str, df: pd.DataFrame, model_proba_up: float = 0.5, timeframe: str = "H1") -> dict:
    """
    Enhanced ML-based signal generation with leading indicators.
    Focuses on price action, momentum, and RSI extremes.
    """
    if len(df) < 20:
        return _create_neutral_signal(symbol, get_market_type(symbol), df.iloc[-1] if len(df) > 0 else {}, 50, 0, "Insufficient data")
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    def safe_float(value, default=0.0):
        if isinstance(value, pd.Series):
            return float(value.iloc[-1])
        return float(value) if pd.notna(value) else default

    rsi = safe_float(current.get("RSI"), 50)
    current_price = safe_float(current["close"])
    current_high = safe_float(current["high"])
    current_low = safe_float(current["low"])
    prev_high = safe_float(prev["high"])
    prev_low = safe_float(prev["low"])

    ema8 = safe_float(current.get("EMA8"), current_price)
    atr = safe_float(current.get("ATR"), 0.0001)
    avg_atr = safe_float(df["ATR"].rolling(20).mean().iloc[-1], atr) if len(df) >= 20 else atr
    volatility = safe_float(current.get("volatility"), 0)

    market_type = get_market_type(symbol)
    
    # Volatility filter
    if atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
        return _create_neutral_signal(symbol, market_type, current, rsi, atr, "High volatility filter")

    # Leading indicators
    price_momentum = (current_price - df['close'].iloc[-5]) / df['close'].iloc[-5] if len(df) >= 5 else 0
    bullish_candle = current_price > current["open"]
    bearish_candle = current_price < current["open"]
    higher_low = current_low >= prev_low * 0.9995
    lower_high = current_high <= prev_high * 1.0005
    uptrend = current_price > ema8
    downtrend = current_price < ema8
    rsi_oversold = rsi < 30
    rsi_overbought = rsi > 70

    # Score based on leading indicators
    long_score = 0
    short_score = 0
    
    if bullish_candle:
        long_score += 2
    if higher_low:
        long_score += 2
    if uptrend:
        long_score += 1
    if price_momentum > 0.002:
        long_score += 2
    if rsi_oversold:
        long_score += 2
    
    if bearish_candle:
        short_score += 2
    if lower_high:
        short_score += 2
    if downtrend:
        short_score += 1
    if price_momentum < -0.002:
        short_score += 2
    if rsi_overbought:
        short_score += 2

    min_score = 4

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

    if model_proba_up > 0.45 and long_score >= min_score:
        signal['direction'] = 'Buy'
        signal['signal_strength'] = min(long_score / 9.0, 1.0)
        signal['entry_type'] = 'Aggressive' if long_score >= 6 else 'Standard'
        signal['confirmation_count'] = long_score
        signal['setup_quality'] = (long_score / 9.0) * 100
        signal['structure'] = 'Uptrend' if uptrend else 'Downtrend'
        
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

    # Calculate SL/TP
    if signal['direction'] in ['Buy', 'Sell']:
        strength = signal['signal_strength']
        sl_atr_mult = max(SL_ATR_BASE - SL_ATR_STRENGTH_FACTOR * strength, 1.0)
        rr = RR_BASE + RR_STRENGTH_FACTOR * strength
        sl_distance = atr * sl_atr_mult
        tp_distance = sl_distance * rr
        
        min_distance = get_minimum_distance(symbol)
        sl_distance = max(sl_distance, min_distance)
        tp_distance = max(tp_distance, min_distance * MIN_RISK_REWARD)
        
        if signal['direction'] == 'Buy':
            signal['stop_loss'] = round_to_symbol_digits(current_price - sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(current_price + tp_distance, symbol)
        else:
            signal['stop_loss'] = round_to_symbol_digits(current_price + sl_distance, symbol)
            signal['take_profit'] = round_to_symbol_digits(current_price - tp_distance, symbol)
        
        signal['risk_reward'] = round(rr, 2)
        
        # Ensure minimum R:R
        if signal['risk_reward'] < MIN_RISK_REWARD:
            return _create_neutral_signal(symbol, market_type, current, rsi, atr, 
                                         f"Below R:R threshold ({signal['risk_reward']:.1f} < {MIN_RISK_REWARD})")
    else:
        signal['stop_loss'] = None
        signal['take_profit'] = None
        signal['risk_reward'] = None

    # Complete signal
    signal['symbol'] = symbol
    signal['market_name'] = display_name(symbol)
    signal['market_type'] = market_type
    signal['price'] = current_price
    signal['rsi'] = rsi
    signal['atr'] = atr
    signal['risk_level'] = get_risk_level(atr, avg_atr)
    
    volume_confirm = atr > avg_atr * 0.8
    signal['opportunity_score'] = calculate_scalp_opportunity(strength, rsi, volatility, atr, volume_confirm, market_type)
    signal['model_confidence'] = model_proba_up if signal['direction'] == 'Buy' else 1.0 - model_proba_up
    
    return signal


def _create_neutral_signal(symbol: str, market_type: str, current, rsi: float, atr: float, reason: str) -> dict:
    """Create a neutral signal with filter reason."""
    current_price = float(current.get('close', 0)) if hasattr(current, 'get') else 0
    return {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": "Neutral",
        "signal_strength": 0.0,
        "setup_quality": 0.0,
        "entry_type": "",
        "confirmation_count": 0,
        "price": current_price,
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, atr),
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "opportunity_score": 0.0,
        "structure": "Neutral",
        "pattern": f"Filter: {reason}",
        "timeframe": "H1",
    }


def passes_trade_filters(signal: dict) -> bool:
    """Check if signal passes trade filters."""
    if signal["direction"] not in ("Buy", "Sell"):
        return False
    if signal["signal_strength"] < MIN_SIGNAL_STRENGTH:
        return False
    if not signal.get("risk_reward") or signal["risk_reward"] < MIN_RISK_REWARD:
        return False
    if signal.get("confirmation_count", 0) < MIN_CONFIRMATIONS:
        return False
    if not signal.get("stop_loss") or not signal.get("take_profit"):
        return False
    
    thresholds = get_market_thresholds(signal["market_type"])
    return signal["signal_strength"] >= thresholds["early_entry"]


def get_all_market_signals() -> Dict[str, dict]:
    """
    Generate signals for all available markets.
    Returns a dictionary mapping symbols to their signals.
    """
    from analysis.services.deriv_client import feed
    
    signals = {}
    
    for symbol in all_symbols():
        try:
            df = feed.get_dataframe(symbol)
            if df is not None and len(df) >= 20:
                # Ensure indicators are calculated
                df = add_technical_indicators(df)
                if len(df) >= 20:
                    # Use default model probability (0.5 = neutral)
                    signal = generate_ml_signal(symbol, df, model_proba_up=0.5)
                    signals[symbol] = signal
                    logging.info(f"Generated signal for {symbol}: {signal['direction']} ({signal['signal_strength']:.2f})")
                else:
                    signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, "Insufficient data after indicators")
            else:
                signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, "Insufficient data")
        except Exception as e:
            logging.error(f"Error generating signal for {symbol}: {e}")
            signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, f"Error: {str(e)}")
    
    return signals
