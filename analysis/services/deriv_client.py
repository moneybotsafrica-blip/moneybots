"""
Deriv WebSocket feed — ported from bot.py's DerivAPI class and extended
into a persistent, multi-symbol feed that keeps a rolling candle buffer
per market in memory for the analysis loop to read.

The browser-side chart talks to Deriv directly (see static/js/chart.js);
this server-side client exists only to feed the ML/signal engine, which
needs candles for *every* market at once, not just the one on screen.

Enhanced with improvements from deriv_market_data script for better
symbol discovery, error handling, and public endpoint support.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
import websockets
from django.conf import settings
from django.core.cache import cache

from markets.catalog import all_symbols, format_deriv_symbol, set_available_markets

logger = logging.getLogger(__name__)

# One-minute candles support intraday day-trading analysis.
CANDLE_GRANULARITY_SECONDS = 60
CANDLE_HISTORY_COUNT = 500
MAX_SIGNAL_SYMBOLS = 10

# Support both public and authenticated endpoints
# Use standard binaryws endpoint with proper app_id format
DEFAULT_PUBLIC_WS_BASE = "wss://ws.binaryws.com/websockets/v3"  # Base URL (app_id added in connection)
DEFAULT_AUTH_WS_BASE = "wss://ws.binaryws.com/websockets/v3"


class DerivFeed:
    """One persistent connection, subscribed to candle history for every
    market in the catalog. Call `get_dataframe(symbol)` from the analysis
    loop to read the latest buffered candles."""

    def __init__(self, ws_url: str | None = None):
        self.api_token = getattr(settings, 'DERIV_API_TOKEN', None)
        self.app_id = getattr(settings, 'DERIV_APP_ID', '1089')
        
        # Build WebSocket URL with app_id
        base_url = ws_url or getattr(settings, 'DERIV_WS_URL', DEFAULT_PUBLIC_WS_BASE)
        if 'app_id' not in base_url:
            separator = '&' if '?' in base_url else '?'
            self.ws_url = f"{base_url}{separator}app_id={self.app_id}"
        else:
            self.ws_url = base_url
        
        self.connection = None
        self._buffers: dict[str, pd.DataFrame] = {}
        self._req_id_map: dict[int, str] = {}
        self._subscription_map: dict[int, str] = {}  # Map subscription ID to symbol
        self._lock = asyncio.Lock()
        self._subscribed_symbols: set[str] = set()
        self._authorized = False
        self.symbols: list[str] = all_symbols()
        self._connection_attempts = 0
        self._max_reconnect_attempts = 5

    # -- public API --------------------------------------------------------
    def get_dataframe(self, symbol: str) -> pd.DataFrame | None:
        # First try to get data from chart cache (browser chart data)
        chart_data = cache.get(f"chart_data_{symbol}")
        if chart_data and chart_data.get('historical'):
            try:
                # Convert chart data to DataFrame format
                historical = chart_data.get('historical', [])
                if historical and len(historical) > 0:
                    df = pd.DataFrame(historical)
                    df['timestamp'] = pd.to_datetime(df['time'], unit='ms')
                    df['epoch'] = df['time'] / 1000
                    logger.debug(f"Using chart data for {symbol}: {len(df)} candles")
                    return df
            except Exception as e:
                logger.warning(f"Failed to process chart data for {symbol}: {e}")
        
        # Fall back to WebSocket buffer data
        df = self._buffers.get(symbol)
        return df.copy() if df is not None else None

    async def run_forever(self):
        """Run the WebSocket connection loop continuously."""
        logger.info("Starting Deriv WebSocket feed...")
        logger.info("Using endpoint: %s", self.ws_url)
        
        while True:
            try:
                await self._connect_and_stream()
                self._connection_attempts = 0  # Reset on successful connection
            except Exception as exc:
                self._connection_attempts += 1
                if self._connection_attempts >= self._max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached. Waiting 60s before retry...")
                    await asyncio.sleep(60)
                    self._connection_attempts = 0
                else:
                    backoff = min(10 * self._connection_attempts, 60)
                    logger.error("Deriv feed connection failed (attempt %d/%d): %s. Reconnecting in %ds...", 
                               self._connection_attempts, self._max_reconnect_attempts, exc, backoff)
                    await asyncio.sleep(backoff)

    # -- internals --------------------------------------------------------
    async def _connect_and_stream(self):
        async with websockets.connect(self.ws_url, ping_interval=20) as ws:
            self.connection = ws
            self._subscribed_symbols.clear()
            self._req_id_map.clear()
            self._subscription_map.clear()
            logger.info("Connected to Deriv WS feed with app_id: %s", self.app_id)

            # Authorize if we have a token
            if self.api_token and self.api_token.strip():
                auth_req = {"authorize": self.api_token}
                await ws.send(json.dumps(auth_req))
                logger.info("Sent authorization request")
            else:
                logger.info("No API token provided, using public access")

            await self._load_active_symbols()
            symbol_count = 0
            for symbol in self.symbols:
                await self._subscribe_candles(symbol)
                symbol_count += 1
                await asyncio.sleep(1.0)  # Increased delay to avoid rate limiting
            logger.info("Subscribed to %d symbols", symbol_count)

            message_count = 0
            async for raw in ws:
                data = json.loads(raw)
                message_count += 1
                if message_count % 100 == 0:
                    logger.debug("Processed %d messages from Deriv feed", message_count)
                await self._handle_message(data)

    async def _load_active_symbols(self):
        """Load Deriv's current symbols before requesting any candles."""
        # Try to load active symbols from the API
        try:
            await self.connection.send(json.dumps({"active_symbols": "brief", "req_id": 0}))
            
            # Wait for response
            while True:
                raw = await asyncio.wait_for(self.connection.recv(), timeout=15)
                data = json.loads(raw)
                if data.get("msg_type") == "active_symbols" or "active_symbols" in data or data.get("error"):
                    break
            
            active = data.get("active_symbols", [])
            if active:
                # Normalize symbol data like deriv_market_data script does
                normalized = []
                for item in active:
                    row = dict(item)
                    row["symbol"] = row.get("symbol") or row.get("underlying_symbol")
                    row["display_name"] = row.get("display_name") or row.get("underlying_symbol_name")
                    normalized.append(row)
                
                set_available_markets(normalized)
                
                # Filter symbols that are likely to work with candle subscriptions
                candle_compatible = []
                for item in normalized:
                    symbol = item.get("underlying_symbol") or item.get("symbol")
                    if not item.get("is_trading_suspended", False):
                        candle_compatible.append(item)
                
                ordered = sorted(
                    candle_compatible,
                    key=lambda item: ("synthetic" not in (item.get("market") or "").lower(), item.get("underlying_symbol") or item.get("symbol")),
                )
                self.symbols = [(item.get("underlying_symbol") or item.get("symbol")) for item in ordered[:MAX_SIGNAL_SYMBOLS]]
                logger.info("Loaded %d live Deriv symbols; scanning %d", len(active), len(self.symbols))
                return
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
            logger.warning("Could not load Deriv active symbols: %s. Using fallback catalog.", exc)
        
        # Fallback to catalog symbols if API call fails
        fallback_symbols = all_symbols()
        # Focus on 1-second volatility indices which are confirmed to work with public API
        working_volatility = [s for s in fallback_symbols if s.startswith("1HZ")]
        
        # If we have working volatility indices, use those
        if working_volatility:
            ordered = working_volatility
        else:
            # Try step indices as they're also confirmed to work
            step_indices = [s for s in fallback_symbols if s.startswith("stpRNG")]
            ordered = step_indices if step_indices else fallback_symbols[:5]
            
        self.symbols = ordered[:MAX_SIGNAL_SYMBOLS]
        logger.info("Using fallback catalog with %d symbols (1-second volatility preferred)", len(self.symbols))

    async def _subscribe_candles(self, symbol: str):
        # Skip if already subscribed
        if symbol in self._subscribed_symbols:
            return
            
        formatted = self._format_symbol_for_deriv(symbol)
        req_id = int(time.time() * 1000) % 1_000_000 + hash(symbol) % 1000
        self._req_id_map[req_id] = symbol
        
        # Try candles first, fall back to ticks if candles fail
        request = {
            "ticks_history": formatted,
            "adjust_start_time": 1,
            "count": CANDLE_HISTORY_COUNT,
            "end": "latest",
            "start": 1,
            "style": "candles",
            "granularity": CANDLE_GRANULARITY_SECONDS,
            "subscribe": 1,
            "req_id": req_id,
        }
        try:
            await self.connection.send(json.dumps(request))
            logger.debug("Sent candle subscription request for %s (req_id: %s)", symbol, req_id)
            # Don't add to subscribed_symbols until we get successful response
        except Exception as exc:
            logger.error("Failed to subscribe %s: %s", symbol, exc)
            # Remove from req_id_map since request failed
            if req_id in self._req_id_map:
                del self._req_id_map[req_id]

    def _format_symbol_for_deriv(self, symbol: str) -> str:
        """Convert internal symbol format to Deriv API format."""
        # The Deriv API expects specific symbol formats for candle subscriptions
        # Try to match the format used in the working deriv_market_data script
        
        # For volatility indices, the API often expects "R_100" format
        # For boom/crash, it expects "BOOM1000" format
        # For step indices, it expects "stpRNG" format
        
        # Most of our symbols should already be in the correct format
        # but we might need to handle some edge cases
        return symbol

    async def _handle_message(self, data: dict):
        if "error" in data:
            error_msg = data["error"].get("message")
            error_code = data["error"].get("code")
            req_id = data.get("req_id")
            
            # Handle invalid symbol errors
            if error_code == "InvalidSymbol":
                symbol = self._req_id_map.get(req_id)
                if symbol:
                    logger.warning("Symbol %s is invalid for candle subscription, skipping", symbol)
                    # Remove from symbols list to avoid retrying
                    if symbol in self.symbols:
                        self.symbols.remove(symbol)
                    # Clean up request mapping
                    if req_id in self._req_id_map:
                        del self._req_id_map[req_id]
                return
            
            logger.warning("Deriv API error: %s (code: %s)", error_msg, error_code)
            return

        msg_type = data.get("msg_type")
        req_id = data.get("req_id")
        
        # Handle authorization response
        if msg_type == "authorize":
            if data.get("error"):
                logger.warning("Authorization failed: %s", data.get("error"))
                self._authorized = False
            else:
                logger.info("Authorization successful")
                self._authorized = True
            return
        
        # Get symbol from request ID or subscription ID
        symbol = self._req_id_map.get(req_id)
        if not symbol and "subscription" in data:
            sub_id = data["subscription"].get("id")
            symbol = self._subscription_map.get(sub_id)

        if not symbol:
            logger.debug("Received message without identifiable symbol: %s", data.get("msg_type"))
            return

        # Handle initial candle history response
        if "candles" in data:
            candles = data["candles"]
            if not candles:
                logger.warning("Empty candles response for %s", symbol)
                return
                
            try:
                df = pd.DataFrame(candles).rename(
                    columns={"epoch": "epoch", "open": "open", "high": "high", "low": "low", "close": "close"}
                )
                df["timestamp"] = pd.to_datetime(df["epoch"], unit="s")
                async with self._lock:
                    self._buffers[symbol] = df
                    # Mark as subscribed only after successful data receipt
                    self._subscribed_symbols.add(symbol)
                logger.info("Loaded %d candles for %s", len(df), symbol)
            except Exception as exc:
                logger.error("Failed to process candles for %s: %s", symbol, exc)

        # Handle real-time OHLC updates
        elif msg_type == "ohlc" and "ohlc" in data:
            ohlc = data.get("ohlc", {})
            async with self._lock:
                df = self._buffers.get(symbol)
                if df is None:
                    logger.debug("Received OHLC for %s but no buffer exists", symbol)
                    return
                    
                try:
                    new_row = {
                        "epoch": ohlc.get("epoch"),
                        "open": float(ohlc.get("open", 0)),
                        "high": float(ohlc.get("high", 0)),
                        "low": float(ohlc.get("low", 0)),
                        "close": float(ohlc.get("close", 0)),
                        "timestamp": pd.to_datetime(ohlc.get("epoch"), unit="s"),
                    }
                    
                    # Update or append candle
                    if len(df) and df.iloc[-1]["epoch"] == new_row["epoch"]:
                        df.iloc[-1] = new_row
                    else:
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        df = df.tail(CANDLE_HISTORY_COUNT).reset_index(drop=True)
                    self._buffers[symbol] = df
                except Exception as exc:
                    logger.error("Failed to process OHLC update for %s: %s", symbol, exc)

        # Store subscription mapping when provided
        elif "subscription" in data:
            sub_id = data["subscription"].get("id")
            if sub_id and symbol:
                self._subscription_map[sub_id] = symbol
                logger.debug("Mapped subscription %s to symbol %s", sub_id, symbol)


# One shared feed instance for the whole process (analysis command + consumers).
feed = DerivFeed()
