#!/usr/bin/env python3
"""Discover Deriv's public instruments and stream live tick data.

The script uses Deriv's public WebSocket market-data endpoint. It does not
place trades and does not require an account token for public market data.

Usage:
    python manage.py deriv_market_data --list
    python manage.py deriv_market_data --stream
    python manage.py deriv_market_data --stream --symbols-file deriv_symbols.json

Environment:
    DERIV_APP_ID: optional legacy application ID. The current public endpoint
                  does not require it; set DERIV_WS_BASE to a legacy endpoint
                  only if you have a valid registered app ID.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.core.management.base import BaseCommand

try:
    from websocket import WebSocket, WebSocketConnectionClosedException, create_connection
except ImportError:
    print("This command requires the websocket-client library. Install it with: pip install websocket-client")
    sys.exit(1)


DEFAULT_APP_ID = os.getenv("DERIV_APP_ID", "")
DEFAULT_WS_BASE = os.getenv("DERIV_WS_BASE", "wss://api.derivws.com/trading/v1/options/ws/public")


def utc_iso(epoch: Any) -> str:
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def request(ws: WebSocket, payload: Dict[str, Any]) -> Dict[str, Any]:
    ws.send(json.dumps(payload))
    while True:
        raw = ws.recv()
        if raw is None:
            raise RuntimeError("Deriv closed the WebSocket connection")
        response = json.loads(raw)
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"Deriv API error {error.get('code')}: {error.get('message')}")
        return response


def connect(app_id: str) -> WebSocket:
    url = DEFAULT_WS_BASE
    if app_id:
        url += f"?app_id={app_id}"
    return create_connection(url, timeout=30, enable_multithread=True)


def discover_symbols(app_id: str) -> List[Dict[str, Any]]:
    ws = connect(app_id)
    try:
        response = request(ws, {"active_symbols": "full"})
        symbols = response.get("active_symbols", [])
        if not isinstance(symbols, list):
            raise RuntimeError("Unexpected active_symbols response")
        # Current public Options responses use underlying_symbol fields;
        # legacy responses use symbol/display_name. Normalize both shapes.
        normalized = []
        for item in symbols:
            row = dict(item)
            row["symbol"] = row.get("symbol") or row.get("underlying_symbol")
            row["display_name"] = row.get("display_name") or row.get("underlying_symbol_name")
            normalized.append(row)
        return normalized
    finally:
        ws.close()


def save_symbols(symbols: List[Dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(symbols, indent=2, ensure_ascii=False), encoding="utf-8")


def print_symbol_table(symbols: Iterable[Dict[str, Any]]) -> None:
    rows = list(symbols)
    print(f"Found {len(rows)} active Deriv symbols.\n")
    print(f"{'Symbol':<18} {'Display name':<42} {'Market':<20} {'Submarket'}")
    print("-" * 105)
    for item in sorted(rows, key=lambda x: (str(x.get("market", "")), str(x.get("symbol", "")))):
        print(
            f"{str(item.get('symbol', '')):<18} "
            f"{str(item.get('display_name', ''))[:40]:<42} "
            f"{str(item.get('market', '')):<20} "
            f"{item.get('submarket', '')}"
        )


def stream_ticks(app_id: str, symbols: List[Dict[str, Any]], output: Path | None = None) -> None:
    names = [str(item["symbol"]) for item in symbols if item.get("symbol")]
    if not names:
        raise RuntimeError("No symbols were returned by active_symbols")

    # The ticks endpoint accepts an array of symbols. One subscription keeps
    # the number of WebSocket requests low while still returning each tick.
    ws = connect(app_id)
    try:
        ws.send(json.dumps({"ticks": names, "subscribe": 1, "req_id": 1}))
        print(f"Streaming {len(names)} symbols. Press Ctrl-C to stop.")
        while True:
            raw = ws.recv()
            if raw is None:
                raise RuntimeError("Deriv closed the WebSocket connection")
            message = json.loads(raw)
            if "error" in message:
                error = message["error"]
                print(f"API error {error.get('code')}: {error.get('message')}", file=sys.stderr)
                continue
            if message.get("msg_type") != "tick":
                continue
            tick = message.get("tick", {})
            row = {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "symbol": tick.get("symbol"),
                "epoch": tick.get("epoch"),
                "time": utc_iso(tick.get("epoch")),
                "quote": tick.get("quote"),
                "ask": tick.get("ask"),
                "bid": tick.get("bid"),
                "pip_size": tick.get("pip_size"),
                "id": tick.get("id"),
            }
            line = json.dumps(row, ensure_ascii=False)
            print(line, flush=True)
            if output:
                with output.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
    finally:
        ws.close()


class Command(BaseCommand):
    help = "Discover Deriv instruments and stream live tick data"

    def add_arguments(self, parser):
        parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Optional Deriv application ID")
        parser.add_argument("--list", action="store_true", help="List active symbols and exit")
        parser.add_argument("--stream", action="store_true", help="Stream live ticks for all active symbols")
        parser.add_argument("--symbols-file", type=Path, default=Path("deriv_symbols.json"), help="Where to save the symbol catalogue")
        parser.add_argument("--output", type=Path, help="Append JSONL ticks to this file")

    def handle(self, *args, **options):
        if not options["list"] and not options["stream"]:
            self.stderr.write("Error: choose --list or --stream")
            return 1

        try:
            symbols = discover_symbols(options["app_id"])
            save_symbols(symbols, options["symbols_file"])
            print_symbol_table(symbols)
            self.stdout.write(f"\nSaved full symbol metadata to {options['symbols_file']}")
            
            if options["stream"]:
                stream_ticks(options["app_id"], symbols, options["output"])
            return 0
        except KeyboardInterrupt:
            self.stdout.write("\nStopped.")
            return 0
        except (OSError, WebSocketConnectionClosedException, RuntimeError, json.JSONDecodeError) as exc:
            self.stderr.write(f"Fatal error: {exc}")
            return 1
