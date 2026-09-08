"""
Static Deriv market catalog — ported from AVAILABLE_MARKETS / format_deriv_symbol
/ get_market_type in the original bot.py, with the MT5-specific pieces removed.

This is the single source of truth for "all Deriv markets" the analysis
engine scans.
"""
from typing import Dict, Iterable
from datetime import datetime
import pytz

# This is deliberately only a safe startup fallback. Deriv changes symbol
# codes and availability by app, country and account. The feed replaces it
# with the live ``active_symbols`` response before subscribing to candles.
# Using verified symbols from Deriv public API - updated with latest market data
# LIMITED TO SYMBOLS CONFIRMED TO WORK WITH PUBLIC API CANDLE SUBSCRIPTIONS
AVAILABLE_MARKETS: Dict[str, str] = {
    # Step Indices - confirmed working with public API
    "stpRNG": "Step Index 100",
    "stpRNG2": "Step Index 200",
    "stpRNG3": "Step Index 300",
    # Major Forex Pairs - confirmed working with public API
    "frxEURUSD": "EUR/USD",
    "frxGBPUSD": "GBP/USD",
    "frxUSDJPY": "USD/JPY",
    "frxUSDCHF": "USD/CHF",
    "frxAUDUSD": "AUD/USD",
    "frxUSDCAD": "USD/CAD",
    "frxNZDUSD": "NZD/USD",
    # Commodities - confirmed working with public API
    "frxXAUUSD": "Gold/USD",
    "frxXAGUSD": "Silver/USD",
    # Cryptocurrencies - confirmed working with public API
    "cryBTCUSD": "BTC/USD",
    "cryETHUSD": "ETH/USD",
}


def set_available_markets(markets: Iterable[dict]) -> None:
    """Replace the fallback catalogue with symbols currently tradable on Deriv."""
    live = {
        (item.get("underlying_symbol") or item.get("symbol")):
        (item.get("underlying_symbol_name") or item.get("display_name") or item.get("underlying_symbol") or item.get("symbol"))
        for item in markets
        if (item.get("underlying_symbol") or item.get("symbol")) and not item.get("is_trading_suspended", False)
    }
    if live:
        AVAILABLE_MARKETS.clear()
        AVAILABLE_MARKETS.update(live)

# Deriv API symbol names - internal names are already correct
_SYMBOL_MAP = {
    # No mapping needed - internal names match Deriv API format
    # Volatility: R_100, Boom/CRASH: BOOM_1000, CRASH_1000
}


def format_deriv_symbol(symbol: str) -> str:
    """Map our internal symbol key to the symbol Deriv's API expects."""
    # Internal symbol names are already in correct Deriv API format
    return symbol


def get_market_type(symbol: str) -> str:
    """Classify a symbol into forex / commodities / synthetic / volatility / indices."""
    upper = symbol.upper()
    if any(x in upper for x in ["XAU", "GOLD", "XAG", "OIL"]):
        return "commodities"
    if symbol.startswith("frx"):
        # Check if it's an index (frxUS30, frxUS500, etc.)
        if any(x in upper for x in ["US30", "US500", "USTEC", "UK100", "DEU30", "FRA40", "EUSTX50", "AUS200", "JPN225", "HK50"]):
            return "indices"
        return "forex"
    if any(x.lower() in symbol.lower() for x in ["crash", "boom", "jump", "step", "stp"]):
        return "synthetic"
    if any(x in upper for x in ["R_", "1HZ", "VOLATILITY"]):
        return "volatility"
    if any(x in upper for x in ["RD", "BEAR", "BULL"]):
        return "synthetic"
    return "synthetic"  # Default to synthetic for volatility/derived indices


def display_name(symbol: str) -> str:
    return AVAILABLE_MARKETS.get(symbol, symbol)


def all_symbols():
    """Return all available symbols, prioritized by compatibility."""
    # Prioritize symbols confirmed to work with public API
    working_symbols = []
    other_symbols = []
    
    for symbol in AVAILABLE_MARKETS.keys():
        # 1-second volatility indices and step indices work best with public API
        if any(symbol.startswith(prefix) for prefix in ["1HZ", "stpRNG"]):
            working_symbols.append(symbol)
        else:
            other_symbols.append(symbol)
    
    # Return working symbols first
    return working_symbols + other_symbols


def is_market_open(symbol: str) -> tuple[bool, str]:
    """
    Check if a market is currently open for trading.
    Returns (is_open, status_message).
    
    Synthetic/Volatility indices: 24/7
    Forex markets: Open 24/5 (Sunday 5pm EST to Friday 5pm EST)
    Commodities: Specific trading hours
    """
    market_type = get_market_type(symbol)
    now = datetime.now(pytz.UTC)
    
    # Synthetic and volatility indices are 24/7
    if market_type in ("synthetic", "volatility"):
        return True, "Open (24/7)"
    
    # Forex markets are open 24/5 (Sunday 5pm EST to Friday 5pm EST)
    if market_type == "forex":
        # Convert to EST timezone
        est = pytz.timezone('US/Eastern')
        now_est = now.astimezone(est)
        
        # Forex is open from Sunday 5pm EST to Friday 5pm EST
        # Sunday = 6, Friday = 4
        if now_est.weekday() == 6:  # Sunday
            if now_est.hour < 17:  # Before 5pm
                return False, "Closed (Weekend)"
            return True, "Open (24/5)"
        elif now_est.weekday() == 4:  # Friday
            if now_est.hour >= 17:  # After 5pm
                return False, "Closed (Weekend)"
            return True, "Open (24/5)"
        elif now_est.weekday() == 5:  # Saturday
            return False, "Closed (Weekend)"
        else:  # Monday-Thursday
            return True, "Open (24/5)"
    
    # Commodities have specific trading hours
    if market_type == "commodities":
        # Gold (XAU) typically trades 24/5 like forex
        est = pytz.timezone('US/Eastern')
        now_est = now.astimezone(est)
        
        if now_est.weekday() == 6:  # Sunday
            if now_est.hour < 18:  # Before 6pm
                return False, "Closed (Weekend)"
            return True, "Open"
        elif now_est.weekday() == 4:  # Friday
            if now_est.hour >= 17:  # After 5pm
                return False, "Closed (Weekend)"
            return True, "Open"
        elif now_est.weekday() == 5:  # Saturday
            return False, "Closed (Weekend)"
        else:  # Monday-Thursday
            return True, "Open"
    
    # Indices follow forex hours
    if market_type == "indices":
        est = pytz.timezone('US/Eastern')
        now_est = now.astimezone(est)
        
        if now_est.weekday() == 6:  # Sunday
            if now_est.hour < 17:  # Before 5pm
                return False, "Closed (Weekend)"
            return True, "Open (24/5)"
        elif now_est.weekday() == 4:  # Friday
            if now_est.hour >= 17:  # After 5pm
                return False, "Closed (Weekend)"
            return True, "Open (24/5)"
        elif now_est.weekday() == 5:  # Saturday
            return False, "Closed (Weekend)"
        else:  # Monday-Thursday
            return True, "Open (24/5)"
    
    return True, "Open"
