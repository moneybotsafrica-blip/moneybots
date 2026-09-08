"""On-demand, analysis-only market scanner for the Signals page.

The page must not depend on a separately running worker.  It fetches a small,
verified set of public Deriv candle streams, then sends those candles through
the existing advanced indicator/strategy engine.  It never authorizes an
account and never submits an order.
"""
from __future__ import annotations

import asyncio
import json
import logging
from itertools import count

import pandas as pd
import websockets
from django.conf import settings

from analysis.services.advanced_market_analysis import analyze_market_comprehensive
from markets.catalog import display_name

logger = logging.getLogger(__name__)

# These symbols are deliberately a known-good public baseline.  If Deriv's
# catalogue endpoint is empty for a public app ID, the scanner can still get
# real candles and analyse them.  The list is not used for trading.
PUBLIC_SCAN_SYMBOLS = (
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
    "1HZ150V", "1HZ250V",
)
SCAN_GRANULARITY = 60
SCAN_CANDLE_COUNT = 300


async def _fetch_candles(symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Fetch independent historical candle sets in one public WS session."""
    app_id = getattr(settings, "DERIV_APP_ID", "1089")
    url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
    results: dict[str, pd.DataFrame] = {}
    requests = {}

    async with websockets.connect(url, ping_interval=20, open_timeout=15) as ws:
        ids = count(1)
        for symbol in symbols:
            req_id = next(ids)
            requests[req_id] = symbol
            await ws.send(json.dumps({
                "ticks_history": symbol,
                "style": "candles",
                "granularity": SCAN_GRANULARITY,
                "count": SCAN_CANDLE_COUNT,
                "end": "latest",
                "adjust_start_time": 1,
                "req_id": req_id,
            }))

        while requests:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for %d Deriv candle responses", len(requests))
                break
            message = json.loads(raw)
            req_id = message.get("req_id")
            symbol = requests.pop(req_id, None)
            if symbol is None:
                continue
            candles = message.get("candles")
            if message.get("error") or not candles:
                logger.info("No candle data for %s: %s", symbol, message.get("error", "empty response"))
                continue
            df = pd.DataFrame(candles)
            for column in ("open", "high", "low", "close"):
                df[column] = pd.to_numeric(df[column], errors="coerce")
            df["epoch"] = pd.to_numeric(df["epoch"], errors="coerce")
            df = df.dropna(subset=["epoch", "open", "high", "low", "close"])
            df["timestamp"] = pd.to_datetime(df["epoch"], unit="s", utc=True)
            results[symbol] = df.sort_values("epoch").reset_index(drop=True)
    return results


async def scan_public_markets() -> list[dict]:
    candles_by_symbol = await _fetch_candles(PUBLIC_SCAN_SYMBOLS)
    signals: list[dict] = []
    for symbol, candles in candles_by_symbol.items():
        try:
            signal = analyze_market_comprehensive(symbol, candles)
        except Exception as exc:  # one bad market must not blank the page
            logger.exception("Analysis failed for %s", symbol)
            signal = {"direction": "Neutral", "signal_strength": 0, "pattern": f"Analysis error: {exc}"}

        # The table and browser panel expect a consistent shape regardless of
        # which strategy (or neutral filter) produced the result.
        signal.update({
            "symbol": symbol,
            "market_name": display_name(symbol),
            "price": float(signal.get("price", candles["close"].iloc[-1])),
            "rsi": float(signal.get("rsi", 50)),
            "atr": float(signal.get("atr", 0)),
            "setup_quality": float(signal.get("setup_quality", signal.get("signal_strength", 0) * 100)),
            "entry_type": signal.get("entry_type", "No setup"),
            "risk_level": signal.get("risk_level", "normal"),
            "opportunity_score": float(signal.get("opportunity_score", 0)),
        })
        signals.append(signal)
    return signals
