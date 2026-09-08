"""
Paper position manager — ported from bot.py's safe_position_size_for_balance(),
MAX_POSITIONS gating, and the SL/TP-hit closing logic inside TradeManager.
No MT5/broker calls anywhere: opening a position only ever writes a
PaperPosition row.
"""
from __future__ import annotations

import logging
from django.conf import settings
from django.utils import timezone

from positions.models import PaperPosition

logger = logging.getLogger(__name__)

# Same micro/small/normal account risk tiers as bot.py, applied to the
# simulated paper balance instead of a real MT5 account.
MICRO_ACCOUNT_MAX_BALANCE = 50
SMALL_ACCOUNT_MAX_BALANCE = 200
MAX_RISK_PCT_MICRO = 0.5
MAX_RISK_PCT_SMALL = 1.0
MAX_RISK_PCT_NORMAL = 1.2
MAX_RISK_PCT_IF_MIN_LOT = 2.0
MAX_POSITIONS = 2

MIN_VOLUME = 0.01
MAX_VOLUME = 1.0
VOLUME_STEP = 0.01
CONTRACT_SIZE = 100000


def _current_paper_balance() -> float:
    """Starting balance adjusted by realized P/L from closed paper trades."""
    realized = sum(
        p.pnl or 0 for p in PaperPosition.objects.exclude(status="open").only("pnl")
    )
    return settings.PAPER_STARTING_BALANCE + realized


def _open_position_count() -> int:
    return PaperPosition.objects.filter(status="open").count()


def safe_position_size(balance: float, entry_price: float, stop_loss: float):
    """Ported from safe_position_size_for_balance(); returns (volume, risk_pct)
    or (None, None) if even the minimum size would risk too much."""
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return MIN_VOLUME, 0.0

    if balance < MICRO_ACCOUNT_MAX_BALANCE:
        risk_pct = MAX_RISK_PCT_MICRO
    elif balance < SMALL_ACCOUNT_MAX_BALANCE:
        risk_pct = MAX_RISK_PCT_SMALL
    else:
        risk_pct = MAX_RISK_PCT_NORMAL

    risk_amount = balance * (risk_pct / 100)
    volume = risk_amount / (CONTRACT_SIZE * sl_distance)
    volume = max(MIN_VOLUME, min(volume, MAX_VOLUME))
    volume = round(round(volume / VOLUME_STEP) * VOLUME_STEP, 2)
    if volume < VOLUME_STEP:
        volume = MIN_VOLUME

    actual_risk_amount = volume * CONTRACT_SIZE * sl_distance
    actual_risk_pct = (actual_risk_amount / balance) * 100 if balance > 0 else 0

    if balance < MICRO_ACCOUNT_MAX_BALANCE and volume == MIN_VOLUME and actual_risk_pct > MAX_RISK_PCT_IF_MIN_LOT:
        logger.info("Skip paper trade: min lot would risk %.1f%% of $%.2f", actual_risk_pct, balance)
        return None, None

    return volume, actual_risk_pct


def maybe_open_position(signal: dict) -> PaperPosition | None:
    """Open a PaperPosition if the signal cleared trade filters, we're
    under MAX_POSITIONS, and we don't already hold this symbol."""
    if _open_position_count() >= MAX_POSITIONS:
        return None
    if PaperPosition.objects.filter(symbol=signal["symbol"], status="open").exists():
        return None

    balance = _current_paper_balance()
    volume, risk_pct = safe_position_size(balance, signal["price"], signal["stop_loss"])
    if volume is None:
        return None

    position = PaperPosition.objects.create(
        symbol=signal["symbol"],
        market_name=signal["market_name"],
        direction=signal["direction"],
        entry_price=signal["price"],
        stop_loss=signal["stop_loss"],
        take_profit=signal["take_profit"],
        volume=volume,
        risk_pct=risk_pct,
        signal_strength=signal["signal_strength"],
    )
    logger.info(
        "Opened paper position %s %s vol=%.2f (risk ~%.2f%% of $%.2f)",
        position.symbol, position.direction, volume, risk_pct, balance,
    )
    return position


def check_and_close_positions(symbol: str, current_price: float):
    """Close any open paper position on `symbol` whose SL or TP the current
    price has crossed. Mirrors TradeManager's position-monitoring loop."""
    positions = PaperPosition.objects.filter(symbol=symbol, status="open")
    for position in positions:
        hit_tp = (
            (position.direction == "Buy" and current_price >= position.take_profit)
            or (position.direction == "Sell" and current_price <= position.take_profit)
        )
        hit_sl = (
            (position.direction == "Buy" and current_price <= position.stop_loss)
            or (position.direction == "Sell" and current_price >= position.stop_loss)
        )
        if not (hit_tp or hit_sl):
            continue

        position.close_price = current_price
        position.pnl = position.unrealized_pnl(current_price)
        position.status = "closed_tp" if hit_tp else "closed_sl"
        position.closed_at = timezone.now()
        position.save()
        logger.info("Closed paper position %s (%s) pnl=%.2f", position.symbol, position.status, position.pnl)
