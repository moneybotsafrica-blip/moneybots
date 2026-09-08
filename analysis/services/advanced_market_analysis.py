"""
Advanced Market Analysis Service
Integrates sophisticated trading strategies and technical indicators from the MT5 analysis script
into the Django application for all markets.
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import asyncio

from markets.catalog import display_name, get_market_type, all_symbols
from analysis.services.indicators import add_technical_indicators
from analysis.services.enhanced_signal_engine import (
    get_symbol_digits, get_symbol_points, get_minimum_distance, 
    round_to_symbol_digits, get_market_thresholds, get_entry_type,
    get_risk_level, calculate_scalp_opportunity
)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Strategy parameters
AVAILABLE_MARKETS = {
    # Commodities
    'XAUUSD': 'Gold/USD',
    'XAGUSD': 'Silver/USD',
    'BRENT': 'Brent Crude Oil',
    'WTI': 'WTI Crude Oil',
    # Synthetic Indices
    'Crash 1000 Index': 'Crash 1000 Index',
    'Crash 500 Index': 'Crash 500 Index',
    'Boom 1000 Index': 'Boom 1000 Index',
    'Boom 500 Index': 'Boom 500 Index',
    'Step Index': 'Step Index',
    'Jump 75 Index': 'Jump 75 Index',
    'Jump 100 Index': 'Jump 100 Index',
    'Jump 50 Index': 'Jump 50 Index',
    # Forex Pairs
    'GBPJPY': 'GBP/JPY',
    'EURUSD': 'EUR/USD',
    'USDJPY': 'USD/JPY',
    'GBPUSD': 'GBP/USD',
    'EURGBP': 'EUR/GBP',
    'AUDUSD': 'AUD/USD',
    'NZDUSD': 'NZD/USD',
    'USDCAD': 'USD/CAD',
    'EURAUD': 'EUR/AUD',
    'AUDJPY': 'AUD/JPY',
    'EURJPY': 'EUR/JPY',
    'USDCHF': 'USD/CHF',
    'EURCHF': 'EUR/CHF',
    # Volatility Indices
    'Volatility 75 Index': 'Volatility 75 Index',
    'Volatility 100 Index': 'Volatility 100 Index',
    'Volatility 50 Index': 'Volatility 50 Index',
    'Volatility 25 Index': 'Volatility 25 Index',
    'Volatility 10 Index': 'Volatility 10 Index',
    # 1-Second Volatility Indices
    'Volatility 10 (1s) Index': 'Volatility 10 (1s) Index',
    'Volatility 25 (1s) Index': 'Volatility 25 (1s) Index',
    'Volatility 50 (1s) Index': 'Volatility 50 (1s) Index',
    'Volatility 75 (1s) Index': 'Volatility 75 (1s) Index',
    'Volatility 100 (1s) Index': 'Volatility 100 (1s) Index',
}

# Strategy thresholds
MIN_CONFIRMATIONS = 2
MIN_SIGNAL_STRENGTH = 0.5
MAX_VOLATILITY_MULTIPLIER = 2.0


def detect_regime(df: pd.DataFrame, symbol: str) -> Dict:
    """
    Enhanced Regime Detection System with Bollinger Band squeeze filter
    """
    try:
        last_candle = df.iloc[-1]
        
        # Calculate ATR percentage
        atr_percent = (last_candle['ATR'] / last_candle['close']) * 100
        
        # Get ADX and EMA values
        adx = last_candle.get('ADX', 0)
        ema20 = last_candle.get('EMA20', last_candle['close'])
        ema50 = last_candle.get('EMA50', last_candle['close'])
        
        # Bollinger Band values for squeeze detection
        bb_width = last_candle.get('BB_Width', 0)
        bb_middle = last_candle.get('BB_Middle', last_candle['close'])
        bb_upper = last_candle.get('BB_Upper', last_candle['close'])
        bb_lower = last_candle.get('BB_Lower', last_candle['close'])
        price = last_candle['close']
        
        # Calculate BB width percentile (squeeze detection)
        bb_width_avg = df['BB_Width'].rolling(window=50).mean().iloc[-1] if 'BB_Width' in df.columns else 0
        is_squeeze = bb_width < (bb_width_avg * 0.7) if bb_width_avg > 0 else False
        
        # Regime filter: Skip if ADX < 20 OR squeeze detected
        should_skip = adx < 20 or is_squeeze
        
        if should_skip:
            regime = "Skip - Low Trend/Squeeze"
            strategies = []
        else:
            # Lowered ADX threshold from 25 to 20 for better strategy activation
            if adx > 20 and ema20 > ema50:
                regime = "Trending Up"
                strategies = ["Synthetic Trend", "Vol Breakout", "EMA Pullback"]
            elif adx > 20 and ema20 < ema50:
                regime = "Trending Down"
                strategies = ["Synthetic Trend", "Vol Breakout", "EMA Pullback"]
            elif adx <= 20 and atr_percent <= 2:
                regime = "Ranging"
                strategies = ["EMA Pullback"]
            elif atr_percent > 2:
                regime = "Volatile"
                strategies = ["Vol Breakout"]
            else:
                regime = "Unknown"
                strategies = ["EMA Pullback"]
        
        # Determine market type
        market_type = get_market_type(symbol)
        
        logging.info(f"""
        Regime Detection for {symbol}:
        Regime: {regime}
        Market Type: {market_type}
        ADX: {adx:.2f} (threshold: 20)
        ATR%: {atr_percent:.2f}%
        BB Width: {bb_width:.4f} (avg: {bb_width_avg:.4f})
        Squeeze: {is_squeeze}
        EMA20: {ema20:.2f}
        EMA50: {ema50:.2f}
        Active Strategies: {', '.join(strategies) if strategies else 'NONE - SKIP'}
        """)
        
        return {
            'regime': regime,
            'market_type': market_type,
            'strategies': strategies,
            'adx': adx,
            'atr_percent': atr_percent,
            'ema20': ema20,
            'ema50': ema50,
            'is_squeeze': is_squeeze,
            'should_skip': should_skip
        }
        
    except Exception as e:
        logging.error(f"Error detecting regime: {e}")
        return {
            'regime': 'Unknown',
            'market_type': get_market_type(symbol),
            'strategies': ['EMA Pullback'],
            'adx': 0,
            'atr_percent': 0,
            'ema20': 0,
            'ema50': 0,
            'is_squeeze': False,
            'should_skip': True
        }


def ema_pullback_strategy(df: pd.DataFrame, regime_data: Dict) -> Dict:
    """
    EMA Pullback Continuation Strategy
    Market Type: Forex, Commodities, Ranging markets
    Best Regime: Ranging, Trending Up/Down
    """
    try:
        last_candle = df.iloc[-1]
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': 'EMA Pullback',
            'strategy': 'EMA Pullback',
            'confirmation_count': 0,
            'confirmations': []
        }
        
        ema20 = last_candle.get('EMA20', last_candle['close'])
        ema50 = last_candle.get('EMA50', last_candle['close'])
        atr = last_candle.get('ATR', 0.0001)
        rsi = last_candle.get('RSI', 50)
        macd_hist = last_candle.get('MACD_Histogram', 0)
        price = last_candle['close']
        
        # Determine if we're in trending or ranging regime
        is_trending = regime_data['regime'] in ['Trending Up', 'Trending Down']
        required_confirmations = 3 if is_trending else 2
        
        # BUY CONDITIONS
        buy_conditions = []
        
        # Trend condition: EMA20 > EMA50 (uptrend) OR market is ranging
        if ema20 > ema50 or not is_trending:
            buy_conditions.append('EMA20 > EMA50 or Ranging')
        
        # Pullback: Price within 1.5×ATR of EMA20
        pullback_distance = abs(price - ema20)
        if pullback_distance <= (1.5 * atr):
            buy_conditions.append('Pullback within 1.5×ATR')
        
        # Momentum: RSI between 35-75 (not overbought)
        if 35 <= rsi <= 75:
            buy_conditions.append('RSI 35-75')
        
        # MACD: Histogram improving or above -0.0001
        prev_macd_hist = df['MACD_Histogram'].iloc[-2] if len(df) > 2 else 0
        if macd_hist > -0.0001 or macd_hist > prev_macd_hist:
            buy_conditions.append('MACD improving')
        
        # Price: Above EMA50 × 0.998
        if price > (ema50 * 0.998):
            buy_conditions.append('Price above EMA50×0.998')
        
        # Check if enough conditions met
        if len(buy_conditions) >= required_confirmations:
            signal['direction'] = 'Buy'
            signal['confirmation_count'] = len(buy_conditions)
            signal['signal_strength'] = len(buy_conditions) / 4
            signal['confirmations'] = buy_conditions
        
        # SELL CONDITIONS (mirror of buy)
        sell_conditions = []
        
        # Trend condition: EMA20 < EMA50 (downtrend) OR market is ranging
        if ema20 < ema50 or not is_trending:
            sell_conditions.append('EMA20 < EMA50 or Ranging')
        
        # Pullback: Price within 1.5×ATR of EMA20
        if pullback_distance <= (1.5 * atr):
            sell_conditions.append('Pullback within 1.5×ATR')
        
        # Momentum: RSI between 25-65 (not oversold)
        if 25 <= rsi <= 65:
            sell_conditions.append('RSI 25-65')
        
        # MACD: Histogram declining or below 0.0001
        prev_macd_hist = df['MACD_Histogram'].iloc[-2] if len(df) > 2 else 0
        if macd_hist < 0.0001 or macd_hist < prev_macd_hist:
            sell_conditions.append('MACD declining')
        
        # Price: Below EMA50 × 1.002
        if price < (ema50 * 1.002):
            sell_conditions.append('Price below EMA50×1.002')
        
        # Check if sell signal is stronger than buy
        if len(sell_conditions) >= required_confirmations and len(sell_conditions) > len(buy_conditions):
            signal['direction'] = 'Sell'
            signal['confirmation_count'] = len(sell_conditions)
            signal['signal_strength'] = len(sell_conditions) / 4
            signal['confirmations'] = sell_conditions
        
        # Calculate SL/TP
        if signal['direction'] != 'Neutral':
            signal['stop_loss'] = price - (1.5 * atr) if signal['direction'] == 'Buy' else price + (1.5 * atr)
            signal['take_profit'] = price + (2.0 * atr) if signal['direction'] == 'Buy' else price - (2.0 * atr)
            signal['risk_reward'] = 2.0 / 1.5
        
        return signal
        
    except Exception as e:
        logging.error(f"Error in EMA Pullback strategy: {e}")
        return {'direction': 'Neutral', 'signal_strength': 0}


def macd_crossover_strategy(df: pd.DataFrame, regime_data: Dict) -> Dict:
    """
    MACD ZeroLine Crossover Strategy
    Market Type: Forex, Commodities
    Best Regime: Trending Up/Down
    """
    try:
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': 'MACD Crossover',
            'strategy': 'MACD Crossover',
            'confirmation_count': 0,
            'confirmations': []
        }
        
        ema50 = last_candle.get('EMA50', last_candle['close'])
        atr = last_candle.get('ATR', 0.0001)
        rsi = last_candle.get('RSI', 50)
        macd = last_candle.get('MACD', 0)
        macd_signal = last_candle.get('MACD_Signal', 0)
        price = last_candle['close']
        adx = last_candle.get('ADX', 0)
        
        # Lowered ADX threshold for MACD - needs some trend but not too strong
        if adx < 15:
            return signal
        
        # BUY CONDITIONS
        buy_conditions = []
        
        # MACD Cross: MACD line crosses ABOVE signal line
        if prev_candle['MACD'] <= prev_candle['MACD_Signal'] and macd > macd_signal:
            buy_conditions.append('MACD cross above signal')
        
        # Price: Above EMA50 × 0.99
        if price > (ema50 * 0.99):
            buy_conditions.append('Price above EMA50×0.99')
        
        # RSI: Between 30-80 (not oversold, not extreme overbought)
        if 30 <= rsi <= 80:
            buy_conditions.append('RSI 30-80')
        
        # Trend: Implicit via EMA50 alignment
        if price > ema50:
            buy_conditions.append('Price above EMA50')
        
        # Check if enough conditions met (need at least 3/4)
        if len(buy_conditions) >= 3:
            signal['direction'] = 'Buy'
            signal['confirmation_count'] = len(buy_conditions)
            signal['signal_strength'] = len(buy_conditions) / 4
            signal['confirmations'] = buy_conditions
        
        # SELL CONDITIONS
        sell_conditions = []
        
        # MACD crosses below signal line
        if prev_candle['MACD'] >= prev_candle['MACD_Signal'] and macd < macd_signal:
            sell_conditions.append('MACD cross below signal')
        
        # Price: Below EMA50 × 1.01
        if price < (ema50 * 1.01):
            sell_conditions.append('Price below EMA50×1.01')
        
        # RSI: 20-70
        if 20 <= rsi <= 70:
            sell_conditions.append('RSI 20-70')
        
        # Trend: Price below EMA50
        if price < ema50:
            sell_conditions.append('Price below EMA50')
        
        # Check if sell signal is stronger
        if len(sell_conditions) >= 3 and len(sell_conditions) > len(buy_conditions):
            signal['direction'] = 'Sell'
            signal['confirmation_count'] = len(sell_conditions)
            signal['signal_strength'] = len(sell_conditions) / 4
            signal['confirmations'] = sell_conditions
        
        # Calculate SL/TP
        if signal['direction'] != 'Neutral':
            signal['stop_loss'] = price - (1.5 * atr) if signal['direction'] == 'Buy' else price + (1.5 * atr)
            signal['take_profit'] = price + (2.0 * atr) if signal['direction'] == 'Buy' else price - (2.0 * atr)
            signal['risk_reward'] = 2.0 / 1.5
        
        return signal
        
    except Exception as e:
        logging.error(f"Error in MACD Crossover strategy: {e}")
        return {'direction': 'Neutral', 'signal_strength': 0}


def synthetic_trend_strategy(df: pd.DataFrame, regime_data: Dict) -> Dict:
    """
    Synthetic Trend Following Strategy
    Market Type: Synthetic Indices (Crash, Boom, Step, Jump)
    Best Regime: Strong Trending Up/Down ONLY
    """
    try:
        last_candle = df.iloc[-1]
        ema10_5_bars_ago = df['EMA10'].iloc[-6] if len(df) >= 6 else last_candle.get('EMA10', last_candle['close'])
        
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': 'Synthetic Trend',
            'strategy': 'Synthetic Trend',
            'confirmation_count': 0,
            'confirmations': []
        }
        
        ema10 = last_candle.get('EMA10', last_candle['close'])
        ema30 = last_candle.get('EMA30', last_candle['close'])
        adx = last_candle.get('ADX', 0)
        rsi = last_candle.get('RSI', 50)
        atr = last_candle.get('ATR', 0.0001)
        price = last_candle['close']
        
        # Lowered ADX threshold from 22 to 18 for better activation
        if adx <= 18:
            return signal
        
        # BUY CONDITIONS
        buy_conditions = []
        
        # Trend: EMA10 > EMA30
        if ema10 > ema30:
            buy_conditions.append('EMA10 > EMA30')
        
        # Strength: ADX > 18 (lowered from 22 for better activation)
        if adx > 18:
            buy_conditions.append('ADX > 18')
        
        # RSI: 40-80 (momentum present but not extreme)
        if 40 <= rsi <= 80:
            buy_conditions.append('RSI 40-80')
        
        # Price: Above EMA10
        if price > ema10:
            buy_conditions.append('Price above EMA10')
        
        # EMA Slope: EMA10 rising vs 5 bars ago
        if ema10 > ema10_5_bars_ago:
            buy_conditions.append('EMA10 rising')
        
        # Guard: Price within 1.5% of EMA10 (not overextended)
        price_distance = abs(price - ema10) / ema10 * 100
        if price_distance <= 1.5:
            buy_conditions.append('Price within 1.5% of EMA10')
        
        # Need at least 4/6 conditions
        if len(buy_conditions) >= 4:
            signal['direction'] = 'Buy'
            signal['confirmation_count'] = len(buy_conditions)
            signal['signal_strength'] = len(buy_conditions) / 6
            signal['confirmations'] = buy_conditions
        
        # SELL CONDITIONS
        sell_conditions = []
        
        # EMA10 < EMA30
        if ema10 < ema30:
            sell_conditions.append('EMA10 < EMA30')
        
        # ADX > 18 (lowered from 22 for better activation)
        if adx > 18:
            sell_conditions.append('ADX > 18')
        
        # RSI: 20-60
        if 20 <= rsi <= 60:
            sell_conditions.append('RSI 20-60')
        
        # Price: Below EMA10
        if price < ema10:
            sell_conditions.append('Price below EMA10')
        
        # EMA Slope: EMA10 falling vs 5 bars ago
        if ema10 < ema10_5_bars_ago:
            sell_conditions.append('EMA10 falling')
        
        # Guard: Price within 1.5% of EMA10
        if price_distance <= 1.5:
            sell_conditions.append('Price within 1.5% of EMA10')
        
        # Need at least 4/6 conditions
        if len(sell_conditions) >= 4 and len(sell_conditions) > len(buy_conditions):
            signal['direction'] = 'Sell'
            signal['confirmation_count'] = len(sell_conditions)
            signal['signal_strength'] = len(sell_conditions) / 6
            signal['confirmations'] = sell_conditions
        
        # Calculate SL/TP
        if signal['direction'] != 'Neutral':
            signal['stop_loss'] = price - (1.5 * atr) if signal['direction'] == 'Buy' else price + (1.5 * atr)
            signal['take_profit'] = price + (2.0 * atr) if signal['direction'] == 'Buy' else price - (2.0 * atr)
            signal['risk_reward'] = 2.0 / 1.5
        
        return signal
        
    except Exception as e:
        logging.error(f"Error in Synthetic Trend strategy: {e}")
        return {'direction': 'Neutral', 'signal_strength': 0}


def volatility_breakout_strategy(df: pd.DataFrame, regime_data: Dict) -> Dict:
    """
    Volatility Breakout Strategy
    Market Type: Volatility Indices (R_10, R_25, R_50, R_75, R_100)
    Best Regime: Volatile, Trending
    """
    try:
        last_candle = df.iloc[-1]
        signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': 'Volatility Breakout',
            'strategy': 'Vol Breakout',
            'confirmation_count': 0,
            'confirmations': []
        }
        
        high_20 = last_candle.get('High_20', last_candle['high'])
        low_20 = last_candle.get('Low_20', last_candle['low'])
        atr = last_candle.get('ATR', 0.0001)
        atr_20 = last_candle.get('ATR_20', atr)
        rsi = last_candle.get('RSI', 50)
        ema20 = last_candle.get('EMA20', last_candle['close'])
        price = last_candle['close']
        open_price = last_candle['open']
        adx = last_candle.get('ADX', 0)
        
        # Lowered ADX threshold for vol breakout - needs trend but not as strong
        if adx < 15:
            return signal
        
        # BUY CONDITIONS
        buy_conditions = []
        
        # Breakout: Price breaks above 20-bar high
        if price > high_20:
            buy_conditions.append('Price above 20-bar high')
        
        # Confirmation: Price actually > high × 1.001 (not just touching)
        if price > (high_20 * 1.001):
            buy_conditions.append('Price > high×1.001')
        
        # RSI: 45-80 (momentum confirms breakout)
        if 45 <= rsi <= 80:
            buy_conditions.append('RSI 45-80')
        
        # Candle: Close > Open (bullish candle)
        if price > open_price:
            buy_conditions.append('Bullish candle')
        
        # Volatility: ATR > 1.1× its 20-bar average (expanding)
        if atr > (atr_20 * 1.1):
            buy_conditions.append('ATR expanding')
        
        # Trend: Price above EMA20
        if price > ema20:
            buy_conditions.append('Price above EMA20')
        
        # Need at least 4/6 conditions
        if len(buy_conditions) >= 4:
            signal['direction'] = 'Buy'
            signal['confirmation_count'] = len(buy_conditions)
            signal['signal_strength'] = len(buy_conditions) / 6
            signal['confirmations'] = buy_conditions
        
        # SELL CONDITIONS
        sell_conditions = []
        
        # Breakout: Price breaks below 20-bar low
        if price < low_20:
            sell_conditions.append('Price below 20-bar low')
        
        # Confirmation: Price < low × 0.999
        if price < (low_20 * 0.999):
            sell_conditions.append('Price < low×0.999')
        
        # RSI: 20-55
        if 20 <= rsi <= 55:
            sell_conditions.append('RSI 20-55')
        
        # Candle: Close < Open (bearish candle)
        if price < open_price:
            sell_conditions.append('Bearish candle')
        
        # Volatility: ATR expanding
        if atr > (atr_20 * 1.1):
            sell_conditions.append('ATR expanding')
        
        # Trend: Price below EMA20
        if price < ema20:
            sell_conditions.append('Price below EMA20')
        
        # Need at least 4/6 conditions
        if len(sell_conditions) >= 4 and len(sell_conditions) > len(buy_conditions):
            signal['direction'] = 'Sell'
            signal['confirmation_count'] = len(sell_conditions)
            signal['signal_strength'] = len(sell_conditions) / 6
            signal['confirmations'] = sell_conditions
        
        # Calculate SL/TP
        if signal['direction'] != 'Neutral':
            signal['stop_loss'] = price - (1.5 * atr) if signal['direction'] == 'Buy' else price + (1.5 * atr)
            signal['take_profit'] = price + (2.0 * atr) if signal['direction'] == 'Buy' else price - (2.0 * atr)
            signal['risk_reward'] = 2.0 / 1.5
        
        return signal
        
    except Exception as e:
        logging.error(f"Error in Volatility Breakout strategy: {e}")
        return {'direction': 'Neutral', 'signal_strength': 0}


def analyze_market_comprehensive(symbol: str, df: pd.DataFrame) -> Dict:
    """
    Comprehensive market analysis using all advanced strategies
    """
    try:
        if len(df) < 20:
            return _create_neutral_signal(symbol, get_market_type(symbol), df.iloc[-1] if len(df) > 0 else {}, 
                                        50, 0, "Insufficient data")
        
        # Ensure all required indicators are present
        df = add_technical_indicators(df)
        
        # Add additional indicators needed for advanced strategies
        if 'High_20' not in df.columns:
            df['High_20'] = df['high'].rolling(window=20).max()
        if 'Low_20' not in df.columns:
            df['Low_20'] = df['low'].rolling(window=20).min()
        if 'ATR_20' not in df.columns:
            df['ATR_20'] = df['ATR'].rolling(window=20).mean()
        if 'EMA10' not in df.columns:
            df['EMA10'] = df['close'].ewm(span=10, adjust=False).mean()
        if 'EMA30' not in df.columns:
            df['EMA30'] = df['close'].ewm(span=30, adjust=False).mean()
        
        # Detect market regime
        regime_data = detect_regime(df, symbol)
        
        # Skip trading if regime filter indicates choppy conditions
        if regime_data['should_skip']:
            return {
                'direction': 'Neutral',
                'signal_strength': 0,
                'pattern': 'Regime Filter',
                'strategy': 'Skip',
                'structure': regime_data['regime'],
                'market': AVAILABLE_MARKETS.get(symbol, symbol),
                'confirmation_count': 0,
                'risk_reward': 0,
                'confirmations': [],
                'skip_reason': regime_data['regime'],
                'regime_data': regime_data
            }
        
        # Initialize signal
        best_signal = {
            'direction': 'Neutral',
            'signal_strength': 0,
            'pattern': '',
            'strategy': '',
            'structure': regime_data['regime'],
            'market': AVAILABLE_MARKETS.get(symbol, symbol),
            'confirmation_count': 0,
            'risk_reward': 0,
            'confirmations': []
        }
        
        # Run appropriate strategies based on regime
        strategies_to_run = regime_data['strategies']
        signals = []
        
        for strategy_name in strategies_to_run:
            if strategy_name == "EMA Pullback":
                signal = ema_pullback_strategy(df, regime_data)
            elif strategy_name == "MACD Crossover":
                signal = macd_crossover_strategy(df, regime_data)
            elif strategy_name == "Synthetic Trend":
                signal = synthetic_trend_strategy(df, regime_data)
            elif strategy_name == "Vol Breakout":
                signal = volatility_breakout_strategy(df, regime_data)
            else:
                continue
            
            if signal['direction'] != 'Neutral':
                signals.append(signal)
        
        # Select best signal (highest strength)
        if signals:
            best_signal = max(signals, key=lambda x: x['signal_strength'])
        
        # Add technical indicator values
        last_candle = df.iloc[-1]
        best_signal['ema8'] = last_candle.get('EMA8', last_candle['close'])
        best_signal['ema21'] = last_candle.get('EMA21', last_candle['close'])
        best_signal['rsi'] = last_candle.get('RSI', 50)
        best_signal['macd_hist'] = last_candle.get('MACD_Histogram', 0)
        best_signal['atr'] = last_candle.get('ATR', 0.0001)
        best_signal['price'] = last_candle['close']
        best_signal['market_type'] = regime_data['market_type']
        best_signal['regime_data'] = regime_data
        
        # Calculate additional metrics
        if best_signal['direction'] in ['Buy', 'Sell']:
            current_price = best_signal['price']
            atr = best_signal['atr']
            
            # Round SL/TP to appropriate precision
            best_signal['stop_loss'] = round_to_symbol_digits(best_signal['stop_loss'], symbol)
            best_signal['take_profit'] = round_to_symbol_digits(best_signal['take_profit'], symbol)
            
            # Calculate opportunity score
            volatility = last_candle.get('volatility', 0)
            volume_confirm = atr > df['ATR'].rolling(20).mean().iloc[-1] * 0.8
            market_type = regime_data['market_type']
            
            best_signal['opportunity_score'] = calculate_scalp_opportunity(
                best_signal['signal_strength'], best_signal['rsi'], 
                volatility, atr, volume_confirm, market_type
            )
            best_signal['setup_quality'] = best_signal['signal_strength'] * 100
            best_signal['entry_type'] = get_entry_type(best_signal['opportunity_score'], 
                                                      best_signal['confirmation_count'] / 5)
            best_signal['risk_level'] = get_risk_level(atr, df['ATR'].rolling(20).mean().iloc[-1])
        
        logging.info(f"""
        Advanced Analysis for {symbol}:
        Regime: {regime_data['regime']}
        Strategy: {best_signal['strategy']}
        Direction: {best_signal['direction']}
        Pattern: {best_signal['pattern']}
        Strength: {best_signal['signal_strength']:.2f}
        Confirmations: {', '.join(best_signal['confirmations'])}
        RSI: {best_signal['rsi']:.2f}
        MACD Hist: {best_signal['macd_hist']:.5f}
        """)
        
        return best_signal
        
    except Exception as e:
        logging.error(f"Error in comprehensive analysis: {e}")
        return _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, f"Error: {str(e)}")


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
        "strategy": "None",
        "confirmations": [],
        "regime_data": None
    }


def get_all_markets_advanced_analysis() -> Dict[str, dict]:
    """
    Generate comprehensive analysis for all available markets.
    Returns a dictionary mapping symbols to their detailed analysis.
    """
    from analysis.services.deriv_client import feed
    
    signals = {}
    
    for symbol in all_symbols():
        try:
            df = feed.get_dataframe(symbol)
            if df is not None and len(df) >= 20:
                # Perform comprehensive analysis
                signal = analyze_market_comprehensive(symbol, df)
                signals[symbol] = signal
                logging.info(f"Advanced analysis for {symbol}: {signal['direction']} ({signal['signal_strength']:.2f})")
            else:
                signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, "Insufficient data")
        except Exception as e:
            logging.error(f"Error analyzing {symbol}: {e}")
            signals[symbol] = _create_neutral_signal(symbol, get_market_type(symbol), {}, 50, 0, f"Error: {str(e)}")
    
    return signals