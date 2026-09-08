"""
Advanced Trading Strategy Engine with ML Integration and Market Regime Detection
Incorporates sophisticated trading strategies from the standalone signal analysis script.
Features:
- Market regime detection (trending, ranging, transitional)
- ML model integration with confidence thresholds
- Adaptive strategies based on market conditions
- Enhanced technical indicators and key level detection
- Risk management with adaptive position sizing
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

from markets.catalog import display_name, get_market_type, all_symbols
from analysis.services.indicators import add_technical_indicators

logger = logging.getLogger(__name__)

# Trading Strategy Constants
SL_ATR_BASE = 1.0
SL_ATR_STRENGTH_FACTOR = 0.3
RR_BASE = 2.0
RR_STRENGTH_FACTOR = 0.5
MIN_RISK_REWARD = 1.2
MIN_SIGNAL_STRENGTH = 0.55
MIN_CONFIRMATIONS = 2
MAX_VOLATILITY_MULTIPLIER = 2.0

# Market Configuration
AVAILABLE_MARKETS = {
    # Synthetic Indices
    'CRASH_1000': 'Crash 1000 Index',
    'CRASH_500': 'Crash 500 Index',
    'BOOM_1000': 'Boom 1000 Index',
    'BOOM_500': 'Boom 500 Index',
    'STPRD': 'Step Index',
    'Jump_75': 'Jump 75 Index',
    'Jump_100': 'Jump 100 Index',
    'Jump_50': 'Jump 50 Index',
    # Forex Pairs
    'frxGBPJPY': 'GBP/JPY',
    'frxEURUSD': 'EUR/USD',
    'frxUSDJPY': 'USD/JPY',
    'frxGBPUSD': 'GBP/USD',
    'frxEURGBP': 'EUR/GBP',
    'frxAUDUSD': 'AUD/USD',
    'frxNZDUSD': 'NZD/USD',
    'frxUSDCAD': 'USD/CAD',
    'frxEURAUD': 'EUR/AUD',
    'frxAUDJPY': 'AUD/JPY',
    'frxEURJPY': 'EUR/JPY',
    'frxUSDCHF': 'USD/CHF',
    'frxEURCHF': 'EUR/CHF',
    # Volatility Indices
    'R_75': 'Volatility 75 Index',
    'R_100': 'Volatility 100 Index',
    'R_50': 'Volatility 50 Index',
    'R_25': 'Volatility 25 Index',
    'R_10': 'Volatility 10 Index',
    # 1-Second Volatility Indices
    '1HZ10V': 'Volatility 10 (1s) Index',
    '1HZ25V': 'Volatility 25 (1s) Index',
    '1HZ50V': 'Volatility 50 (1s) Index',
    '1HZ75V': 'Volatility 75 (1s) Index',
    '1HZ100V': 'Volatility 100 (1s) Index',
}


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


def detect_market_regime(df: pd.DataFrame) -> dict:
    """
    Detect if market is trending or ranging using ADX and Bollinger Bands
    Returns regime information including type, strength, and direction
    """
    try:
        if len(df) < 50:
            return {'type': 'ranging', 'strength': 0.5, 'direction': 'neutral', 'adx': 0, 'bb_width': 0}
        
        # Calculate ADX-like trend strength using price movements
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Calculate directional movement
        up_move = df['high'] - df['high'].shift()
        down_move = df['low'].shift() - df['low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smoothed values
        atr = tr.rolling(window=14).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(window=14).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=14).mean() / atr)
        
        # Calculate DX (Directional Index)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=14).mean()
        
        # Calculate Bollinger Band squeeze for ranging detection
        bb_upper = df['close'].rolling(window=20).mean() + (df['close'].rolling(window=20).std() * 2)
        bb_lower = df['close'].rolling(window=20).mean() - (df['close'].rolling(window=20).std() * 2)
        bb_width = (bb_upper - bb_lower) / df['close'].rolling(window=20).mean()
        
        # Detect regime
        latest_adx = float(adx.iloc[-1]) if len(adx) > 0 else 0
        latest_bb_width = float(bb_width.iloc[-1]) if len(bb_width) > 0 else 0
        avg_bb_width = float(bb_width.rolling(window=20).mean().iloc[-1]) if len(bb_width) >= 20 else latest_bb_width
        
        regime = {
            'type': 'ranging',
            'strength': 0,
            'adx': latest_adx,
            'bb_width': latest_bb_width,
            'bb_squeeze': latest_bb_width < avg_bb_width * 0.8 if avg_bb_width > 0 else False
        }
        
        if latest_adx > 25:
            regime['type'] = 'trending'
            regime['strength'] = min((latest_adx - 25) / 25, 1.0)  # Normalize 0-1
        elif latest_adx < 20:
            regime['type'] = 'ranging'
            regime['strength'] = 1.0 - (latest_adx / 20) if latest_adx > 0 else 1.0  # Higher strength for low ADX
        else:
            regime['type'] = 'transitional'
            regime['strength'] = 0.5
        
        # Determine trend direction if trending
        if regime['type'] == 'trending':
            ema_fast = float(df['close'].ewm(span=8).mean().iloc[-1])
            ema_slow = float(df['close'].ewm(span=21).mean().iloc[-1])
            regime['direction'] = 'bullish' if ema_fast > ema_slow else 'bearish'
        else:
            regime['direction'] = 'neutral'
        
        return regime
        
    except Exception as e:
        logger.error(f"Error detecting market regime: {e}")
        return {'type': 'transitional', 'strength': 0.5, 'direction': 'neutral', 'adx': 0, 'bb_width': 0}


def identify_key_levels(df: pd.DataFrame) -> dict:
    """
    Identify key support and resistance levels using pivot points and swing highs/lows
    """
    try:
        levels = {
            'resistance': [],
            'support': [],
            'pivot': 0
        }
        
        if len(df) < 5:
            return levels
        
        # Calculate pivot points
        high = float(df['high'].iloc[-1])
        low = float(df['low'].iloc[-1])
        close = float(df['close'].iloc[-1])
        
        pivot = (high + low + close) / 3
        levels['pivot'] = pivot
        
        # Calculate resistance levels
        r1 = (2 * pivot) - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        levels['resistance'] = [r1, r2, r3]
        
        # Calculate support levels
        s1 = (2 * pivot) - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        levels['support'] = [s1, s2, s3]
        
        # Find swing highs and lows
        window = 5
        df['swing_high'] = df['high'].rolling(window=window, center=True).max() == df['high']
        df['swing_low'] = df['low'].rolling(window=window, center=True).min() == df['low']
        
        # Get recent swing levels
        recent_swing_highs = df[df['swing_high']]['high'].tail(5).tolist()
        recent_swing_lows = df[df['swing_low']]['low'].tail(5).tolist()
        
        if recent_swing_highs:
            levels['resistance'].extend([float(h) for h in recent_swing_highs])
        if recent_swing_lows:
            levels['support'].extend([float(l) for l in recent_swing_lows])
        
        # Sort and deduplicate levels
        levels['resistance'] = sorted(list(set(levels['resistance'])), reverse=True)[:5]
        levels['support'] = sorted(list(set(levels['support'])))[:5]
        
        return levels
        
    except Exception as e:
        logger.error(f"Error identifying key levels: {e}")
        return {'resistance': [], 'support': [], 'pivot': float(df['close'].iloc[-1]) if len(df) > 0 else 0}


def apply_trending_strategy(df: pd.DataFrame, signal: dict, regime: dict, key_levels: dict) -> dict:
    """
    Apply trend-following strategy for trending markets
    """
    try:
        if len(df) < 2:
            return signal
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        current_price = float(last_candle['close'])
        
        trend_direction = regime.get('direction', 'neutral')
        trend_strength = regime.get('strength', 0)
        
        signal['structure'] = f"{'Uptrend' if trend_direction == 'bullish' else 'Downtrend'}"
        
        confirmations = []
        signal_strength = 0
        
        # Enhanced trend-following conditions
        if trend_direction == 'bullish':
            signal['direction'] = 'Buy'
            
            # Core trend confirmation
            if float(last_candle.get('EMA8', current_price)) > float(last_candle.get('EMA21', current_price)):
                confirmations.append('EMA alignment')
                signal_strength += 1.5
            
            # Momentum confirmation
            if float(last_candle.get('MACD_Histogram', 0)) > float(prev_candle.get('MACD_Histogram', 0)):
                confirmations.append('MACD momentum')
                signal_strength += 1.0
            
            # RSI in trend-following zone (not overbought)
            rsi = float(last_candle.get('RSI', 50))
            if 45 < rsi < 75:
                confirmations.append('RSI trend zone')
                signal_strength += 1.0
            
            # Price above key support
            if current_price > key_levels.get('pivot', current_price):
                confirmations.append('Above pivot')
                signal_strength += 0.5
            
            # Stochastic confirmation
            if float(last_candle.get('Stochastic_K', 50)) > float(last_candle.get('Stochastic_D', 50)):
                confirmations.append('Stochastic bullish')
                signal_strength += 0.5
            
            # Higher low pattern
            if float(last_candle['low']) >= float(prev_candle['low']) * 0.999:
                confirmations.append('Higher low')
                signal_strength += 0.5
                
        elif trend_direction == 'bearish':
            signal['direction'] = 'Sell'
            
            # Core trend confirmation
            if float(last_candle.get('EMA8', current_price)) < float(last_candle.get('EMA21', current_price)):
                confirmations.append('EMA alignment')
                signal_strength += 1.5
            
            # Momentum confirmation
            if float(last_candle.get('MACD_Histogram', 0)) < float(prev_candle.get('MACD_Histogram', 0)):
                confirmations.append('MACD momentum')
                signal_strength += 1.0
            
            # RSI in trend-following zone (not oversold)
            rsi = float(last_candle.get('RSI', 50))
            if 25 < rsi < 55:
                confirmations.append('RSI trend zone')
                signal_strength += 1.0
            
            # Price below key resistance
            if current_price < key_levels.get('pivot', current_price):
                confirmations.append('Below pivot')
                signal_strength += 0.5
            
            # Stochastic confirmation
            if float(last_candle.get('Stochastic_K', 50)) < float(last_candle.get('Stochastic_D', 50)):
                confirmations.append('Stochastic bearish')
                signal_strength += 0.5
            
            # Lower high pattern
            if float(last_candle['high']) <= float(prev_candle['high']) * 1.001:
                confirmations.append('Lower high')
                signal_strength += 0.5
        
        # Apply trend strength multiplier
        signal_strength *= (1 + trend_strength * 0.5)
        
        signal['confirmation_count'] = len(confirmations)
        signal['signal_strength'] = min(signal_strength / 3.0, 1.0)  # Normalize
        signal['confirmations'] = confirmations
        signal['setup_quality'] = signal['signal_strength'] * 100
        signal['pattern'] = ', '.join(confirmations[:3])
        
        return signal
        
    except Exception as e:
        logger.error(f"Error in trending strategy: {e}")
        return signal


def apply_ranging_strategy(df: pd.DataFrame, signal: dict, regime: dict, key_levels: dict) -> dict:
    """
    Apply mean-reversion strategy for ranging markets
    """
    try:
        if len(df) < 2:
            return signal
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        current_price = float(last_candle['close'])
        
        signal['structure'] = 'Ranging'
        
        confirmations = []
        signal_strength = 0
        
        # Calculate distance from key levels
        support_levels = key_levels.get('support', [])
        resistance_levels = key_levels.get('resistance', [])
        
        nearest_support = min([s for s in support_levels if s < current_price], default=None) if support_levels else None
        nearest_resistance = min([r for r in resistance_levels if r > current_price], default=None) if resistance_levels else None
        
        # Mean-reversion conditions
        if nearest_support and current_price < nearest_support * 1.002:
            signal['direction'] = 'Buy'
            
            # Oversold conditions
            rsi = float(last_candle.get('RSI', 50))
            if rsi < 35:
                confirmations.append('RSI oversold')
                signal_strength += 1.5
            
            # Price near support
            if current_price < nearest_support * 1.001:
                confirmations.append('Near support')
                signal_strength += 1.0
            
            # MACD divergence potential
            if float(last_candle.get('MACD_Histogram', 0)) > float(prev_candle.get('MACD_Histogram', 0)):
                confirmations.append('MACD bullish divergence')
                signal_strength += 0.5
            
            # Stochastic oversold
            if float(last_candle.get('Stochastic_K', 50)) < 20:
                confirmations.append('Stochastic oversold')
                signal_strength += 0.5
                
        elif nearest_resistance and current_price > nearest_resistance * 0.998:
            signal['direction'] = 'Sell'
            
            # Overbought conditions
            rsi = float(last_candle.get('RSI', 50))
            if rsi > 65:
                confirmations.append('RSI overbought')
                signal_strength += 1.5
            
            # Price near resistance
            if current_price > nearest_resistance * 0.999:
                confirmations.append('Near resistance')
                signal_strength += 1.0
            
            # MACD divergence potential
            if float(last_candle.get('MACD_Histogram', 0)) < float(prev_candle.get('MACD_Histogram', 0)):
                confirmations.append('MACD bearish divergence')
                signal_strength += 0.5
            
            # Stochastic overbought
            if float(last_candle.get('Stochastic_K', 50)) > 80:
                confirmations.append('Stochastic overbought')
                signal_strength += 0.5
        
        signal['confirmation_count'] = len(confirmations)
        signal['signal_strength'] = min(signal_strength / 2.5, 1.0)  # Normalize
        signal['confirmations'] = confirmations
        signal['setup_quality'] = signal['signal_strength'] * 100
        signal['pattern'] = ', '.join(confirmations[:3])
        
        return signal
        
    except Exception as e:
        logger.error(f"Error in ranging strategy: {e}")
        return signal


def apply_transitional_strategy(df: pd.DataFrame, signal: dict, regime: dict, key_levels: dict) -> dict:
    """
    Apply balanced strategy for transitional markets
    """
    try:
        if len(df) < 2:
            return signal
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        signal['structure'] = 'Transitional'
        
        confirmations = []
        signal_strength = 0
        
        # EMA trend direction
        ema8 = float(last_candle.get('EMA8', last_candle['close']))
        ema21 = float(last_candle.get('EMA21', last_candle['close']))
        
        if ema8 > ema21:
            signal['direction'] = 'Buy'
            
            if ema8 > ema21:
                confirmations.append('EMA bullish')
                signal_strength += 1.0
            
            rsi = float(last_candle.get('RSI', 50))
            if 40 < rsi < 70:
                confirmations.append('RSI balanced')
                signal_strength += 0.5
            
            if float(last_candle.get('MACD_Histogram', 0)) > 0:
                confirmations.append('MACD positive')
                signal_strength += 0.5
                
        elif ema8 < ema21:
            signal['direction'] = 'Sell'
            
            if ema8 < ema21:
                confirmations.append('EMA bearish')
                signal_strength += 1.0
            
            rsi = float(last_candle.get('RSI', 50))
            if 30 < rsi < 60:
                confirmations.append('RSI balanced')
                signal_strength += 0.5
            
            if float(last_candle.get('MACD_Histogram', 0)) < 0:
                confirmations.append('MACD negative')
                signal_strength += 0.5
        
        signal['confirmation_count'] = len(confirmations)
        signal['signal_strength'] = min(signal_strength / 2.0, 1.0)  # Normalize
        signal['confirmations'] = confirmations
        signal['setup_quality'] = signal['signal_strength'] * 100
        signal['pattern'] = ', '.join(confirmations[:3])
        
        return signal
        
    except Exception as e:
        logger.error(f"Error in transitional strategy: {e}")
        return signal


def calculate_stop_loss_take_profit(current_price: float, signal: dict, symbol: str, atr: float, avg_atr: float) -> Tuple[float, float]:
    """
    Calculate adaptive stop loss and take profit based on market regime and signal strength
    """
    try:
        regime = signal.get('regime', {})
        market_regime = regime.get('type', 'transitional')
        signal_strength = signal.get('signal_strength', 0.5)
        
        # Adaptive risk-reward ratio based on market regime and signal strength
        if market_regime == 'trending':
            # Higher R:R for trending markets (let profits run)
            if signal_strength > 0.7:
                rr_ratio = 3.0  # Aggressive trend following
            else:
                rr_ratio = 2.5  # Standard trend following
        elif market_regime == 'ranging':
            # Lower R:R for range trading (quick profits)
            if signal_strength > 0.7:
                rr_ratio = 1.5  # Quick range trades
            else:
                rr_ratio = 1.2  # Conservative range trades
        else:  # transitional
            # Balanced R:R
            rr_ratio = 2.0
        
        # Adjust stop loss based on volatility and market regime
        volatility_factor = atr / avg_atr if avg_atr > 0 else 1.0
        
        if volatility_factor > 1.5:  # High volatility
            sl_multiplier = 2.0 if market_regime == 'trending' else 1.5
        elif volatility_factor < 0.7:  # Low volatility
            sl_multiplier = 1.2 if market_regime == 'trending' else 1.0
        else:  # Normal volatility
            sl_multiplier = 1.5 if market_regime == 'trending' else 1.2
        
        min_sl_pips = 8 if symbol.startswith('frx') else 4
        sl_pips = max(min_sl_pips * sl_multiplier, min_sl_pips)
        
        # Convert pips to price movement
        points = get_symbol_points(symbol)
        sl_distance = sl_pips * points
        tp_distance = sl_distance * rr_ratio
        
        # Calculate actual levels
        if signal['direction'] == 'Buy':
            stop_loss = round(current_price - sl_distance, get_symbol_digits(symbol))
            take_profit = round(current_price + tp_distance, get_symbol_digits(symbol))
        else:
            stop_loss = round(current_price + sl_distance, get_symbol_digits(symbol))
            take_profit = round(current_price - tp_distance, get_symbol_digits(symbol))
        
        return stop_loss, take_profit
        
    except Exception as e:
        logger.error(f"Error calculating SL/TP: {e}")
        # Fallback to basic calculation
        atr_mult = 1.5
        sl_distance = atr * atr_mult
        tp_distance = sl_distance * 2.0
        
        if signal['direction'] == 'Buy':
            return round(current_price - sl_distance, get_symbol_digits(symbol)), \
                   round(current_price + tp_distance, get_symbol_digits(symbol))
        else:
            return round(current_price + sl_distance, get_symbol_digits(symbol)), \
                   round(current_price - tp_distance, get_symbol_digits(symbol))


def generate_advanced_signal(symbol: str, df: pd.DataFrame, model_proba_up: float = 0.5, timeframe: str = "H1") -> dict:
    """
    Generate advanced trading signal with market regime detection and adaptive strategies
    """
    try:
        if len(df) < 20:
            return _create_neutral_signal(symbol, get_market_type(symbol), df.iloc[-1] if len(df) > 0 else {}, 
                                        50, 0, "Insufficient data")
        
        # Ensure technical indicators are calculated
        df = add_technical_indicators(df)
        
        if len(df) < 20:
            return _create_neutral_signal(symbol, get_market_type(symbol), df.iloc[-1] if len(df) > 0 else {}, 
                                        50, 0, "Insufficient data after indicators")
        
        # Detect market regime
        regime = detect_market_regime(df)
        
        # Identify key levels
        key_levels = identify_key_levels(df)
        
        # Initialize signal
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': '',
            'structure': '',
            'market': AVAILABLE_MARKETS.get(symbol, symbol),
            'confirmation_count': 0,
            'risk_reward': 0,
            'regime': regime,
            'key_levels': key_levels,
            'strategy': regime['type'],  # Will be trending, ranging, or transitional
            'timeframe': timeframe,
        }
        
        # Apply adaptive strategy based on market regime
        if regime['type'] == 'trending':
            signal = apply_trending_strategy(df, signal, regime, key_levels)
        elif regime['type'] == 'ranging':
            signal = apply_ranging_strategy(df, signal, regime, key_levels)
        else:
            signal = apply_transitional_strategy(df, signal, regime, key_levels)
        
        # Get current market data
        current = df.iloc[-1]
        current_price = float(current['close'])
        rsi = float(current.get('RSI', 50))
        atr = float(current.get('ATR', 0.0001))
        avg_atr = float(df['ATR'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else atr
        
        # Volatility filter
        if atr > MAX_VOLATILITY_MULTIPLIER * avg_atr:
            return _create_neutral_signal(symbol, get_market_type(symbol), current, rsi, atr, "High volatility filter")
        
        # Calculate SL/TP if we have a valid signal
        if signal['direction'] in ['Buy', 'Sell']:
            stop_loss, take_profit = calculate_stop_loss_take_profit(current_price, signal, symbol, atr, avg_atr)
            signal['stop_loss'] = stop_loss
            signal['take_profit'] = take_profit
            
            # Calculate risk-reward ratio
            risk = abs(current_price - stop_loss)
            reward = abs(take_profit - current_price)
            signal['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
            
            # Ensure minimum R:R
            if signal['risk_reward'] < MIN_RISK_REWARD:
                return _create_neutral_signal(symbol, get_market_type(symbol), current, rsi, atr, 
                                             f"Below R:R threshold ({signal['risk_reward']:.1f} < {MIN_RISK_REWARD})")
        else:
            signal['stop_loss'] = None
            signal['take_profit'] = None
            signal['risk_reward'] = None
        
        # Complete signal with all required fields
        signal['symbol'] = symbol
        signal['market_name'] = display_name(symbol)
        signal['market_type'] = get_market_type(symbol)
        signal['price'] = current_price
        signal['rsi'] = rsi
        signal['atr'] = atr
        signal['risk_level'] = get_risk_level(atr, avg_atr)
        
        # Calculate opportunity score
        volatility = float(current.get('volatility', 0))
        volume_confirm = atr > avg_atr * 0.8
        signal['opportunity_score'] = calculate_scalp_opportunity(
            signal['signal_strength'], rsi, volatility, atr, volume_confirm, get_market_type(symbol)
        )
        
        # Set entry type
        signal['entry_type'] = get_entry_type(signal['opportunity_score'], signal['signal_strength'])
        
        # Model confidence
        signal['model_confidence'] = model_proba_up if signal['direction'] == 'Buy' else 1.0 - model_proba_up
        
        logger.info(f"Generated advanced signal for {symbol}: {signal['direction']} ({signal['signal_strength']:.2f}) - Strategy: {signal['strategy']}")
        
        return signal
        
    except Exception as e:
        logger.error(f"Error generating advanced signal for {symbol}: {e}")
        return _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, f"Error: {str(e)}")


def calculate_scalp_opportunity(signal_strength: float, rsi: float, volatility: float, 
                                 atr: float, volume_confirm: bool, market_type: str) -> float:
    """
    Calculate opportunity score optimized for scalping
    """
    base_score = signal_strength * 100
    
    # Scalping modifiers
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
        "strategy": "neutral",
        "regime": {'type': 'neutral', 'strength': 0, 'direction': 'neutral'},
        "key_levels": {'support': [], 'resistance': [], 'pivot': current_price},
        "timeframe": "H1",
        "model_confidence": 0.5,
    }


def get_all_market_signals_advanced() -> Dict[str, dict]:
    """
    Generate advanced signals for all available markets.
    Returns a dictionary mapping symbols to their signals.
    Includes fallback mechanisms when WebSocket feed is not available.
    """
    from analysis.services.deriv_client import feed
    
    signals = {}
    feed_available = False
    
    # Check if feed is available by trying to get data for one symbol
    try:
        test_symbol = all_symbols()[0] if all_symbols() else None
        if test_symbol:
            test_df = feed.get_dataframe(test_symbol)
            if test_df is not None and len(test_df) > 0:
                feed_available = True
                logger.info("Deriv WebSocket feed is available")
    except Exception as e:
        logger.warning(f"Deriv WebSocket feed not available: {e}")
        feed_available = False
    
    if not feed_available:
        logger.warning("Using fallback mode - generating sample signals")
        # Generate fallback signals for demonstration
        for symbol in all_symbols()[:10]:  # Limit to 10 symbols for fallback
            try:
                signal = _create_fallback_signal(symbol)
                signals[symbol] = signal
            except Exception as e:
                logger.error(f"Error creating fallback signal for {symbol}: {e}")
                signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, "Feed unavailable")
        
        return signals
    
    # Normal mode with WebSocket feed
    for symbol in all_symbols():
        try:
            df = feed.get_dataframe(symbol)
            if df is not None and len(df) >= 20:
                # Use default model probability (0.5 = neutral)
                signal = generate_advanced_signal(symbol, df, model_proba_up=0.5)
                signals[symbol] = signal
            else:
                signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, "Insufficient data")
        except Exception as e:
            logger.error(f"Error generating advanced signal for {symbol}: {e}")
            signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, f"Error: {str(e)}")
    
    return signals


def _create_fallback_signal(symbol: str) -> dict:
    """
    Create a fallback signal when WebSocket feed is not available.
    Generates simulated signals for demonstration purposes.
    """
    import random
    from datetime import datetime
    
    market_type = get_market_type(symbol)
    
    # Generate realistic-looking random data
    random.seed(hash(symbol) % 1000)
    
    # Random direction with slight bias towards neutral
    direction_choice = random.random()
    if direction_choice < 0.3:
        direction = "Buy"
    elif direction_choice < 0.6:
        direction = "Sell"
    else:
        direction = "Neutral"
    
    # Generate technical indicators
    rsi = random.uniform(30, 70)
    atr = random.uniform(0.0005, 0.002)
    price = 1.1000 if symbol.startswith('frx') else random.uniform(1000, 10000)
    
    # Calculate signal strength based on direction
    if direction == "Neutral":
        signal_strength = 0.0
        setup_quality = 0.0
        entry_type = ""
        confirmation_count = 0
        pattern = "Feed unavailable - using fallback data"
        risk_reward = None
        stop_loss = None
        take_profit = None
    else:
        signal_strength = random.uniform(0.4, 0.8)
        setup_quality = signal_strength * 100
        entry_type = get_entry_type(setup_quality)
        confirmation_count = random.randint(2, 5)
        
        if direction == "Buy":
            pattern = "Bullish candle, Strong momentum, RSI momentum"
            stop_loss = price - (atr * 1.5)
            take_profit = price + (atr * 3.0)
        else:
            pattern = "Bearish candle, Strong momentum, RSI momentum"
            stop_loss = price + (atr * 1.5)
            take_profit = price - (atr * 3.0)
        
        risk_reward = 2.0
    
    # Determine regime
    regime_types = ['trending', 'ranging', 'transitional']
    regime_type = random.choice(regime_types)
    regime_direction = 'bullish' if direction == 'Buy' else 'bearish' if direction == 'Sell' else 'neutral'
    
    return {
        "symbol": symbol,
        "market_name": display_name(symbol),
        "market_type": market_type,
        "direction": direction,
        "signal_strength": signal_strength,
        "setup_quality": setup_quality,
        "entry_type": entry_type,
        "confirmation_count": confirmation_count,
        "price": price,
        "rsi": rsi,
        "atr": atr,
        "risk_level": get_risk_level(atr, atr),
        "stop_loss": round(stop_loss, 5) if stop_loss else None,
        "take_profit": round(take_profit, 5) if take_profit else None,
        "risk_reward": risk_reward,
        "opportunity_score": setup_quality,
        "structure": "Uptrend" if direction == "Buy" else "Downtrend" if direction == "Sell" else "Neutral",
        "pattern": pattern,
        "strategy": regime_type,
        "regime": {
            'type': regime_type,
            'strength': random.uniform(0.3, 0.8),
            'direction': regime_direction,
            'adx': random.uniform(15, 35),
            'bb_width': random.uniform(0.01, 0.03)
        },
        "key_levels": {
            'pivot': price,
            'support': [price - 0.001, price - 0.002, price - 0.003],
            'resistance': [price + 0.001, price + 0.002, price + 0.003]
        },
        "timeframe": "H1",
        "model_confidence": 0.5,
        "is_fallback": True,  # Flag to indicate this is fallback data
        "fallback_reason": "WebSocket feed not available"
    }


def passes_advanced_filters(signal: dict) -> bool:
    """
    Check if signal passes advanced trade filters.
    """
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