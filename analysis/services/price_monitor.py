"""
Price monitoring service for tracking TP/SL hits on active signals.
"""
import logging
from typing import Dict, List, Optional

from asgiref.sync import async_to_sync
from django.utils import timezone

from analysis.models import MarketSignal
from analysis.services.broadcaster import broadcast

logger = logging.getLogger(__name__)


def get_pip_value(symbol: str) -> float:
    """Return the pip value for a given symbol."""
    # Forex pairs typically have 4 decimal places (3 for JPY pairs)
    if symbol.startswith("frx"):
        if "JPY" in symbol.upper():
            return 0.01  # JPY pairs: 2 decimal places
        return 0.0001  # Other forex: 4 decimal places
    # Commodities have 2 decimal places
    if "XAU" in symbol or "XAG" in symbol or "WTI" in symbol or "NG" in symbol:
        return 0.01
    # Synthetic indices have 5 decimal places
    if symbol.startswith("BOOM") or symbol.startswith("CRASH") or symbol.startswith("Jump") or symbol.startswith("JD"):
        return 0.00001
    # Volatility indices have 5 decimal places
    if symbol.startswith("R_") or symbol.startswith("1HZ"):
        return 0.00001
    # Step indices have 5 decimal places
    if symbol.startswith("STP"):
        return 0.00001
    # Bear/Bull indices have 5 decimal places
    if symbol.startswith("RD"):
        return 0.00001
    # Default to 0.0001
    return 0.0001


class PriceMonitor:
    """Monitor active signals and detect TP/SL hits based on current prices."""

    def broadcast_price_update(self, symbol: str, current_price: float) -> None:
        """Broadcast current price update for active signals."""
        try:
            active_signals = MarketSignal.objects.filter(
                symbol=symbol,
                status="active",
                direction__in=["Buy", "Sell"],
            )

            if active_signals.exists():
                payload = {
                    "type": "price_update",
                    "symbol": symbol,
                    "current_price": current_price,
                    "timestamp": timezone.now().isoformat(),
                }
                async_to_sync(broadcast)(payload)
                logger.info("Broadcasted price update for %s: %s (active signals: %d)", 
                           symbol, current_price, active_signals.count())
            else:
                logger.debug("No active signals for %s, skipping price broadcast", symbol)
        except Exception as exc:
            logger.error("Error broadcasting price update for %s: %s", symbol, exc)

    def check_symbol(self, symbol: str, current_price: float) -> List[Dict]:
        """Check active signals for one symbol; mark TP/SL hits as completed."""
        hit_signals = []

        active_signals = MarketSignal.objects.filter(
            symbol=symbol,
            status="active",
            direction__in=["Buy", "Sell"],
        ).exclude(stop_loss__isnull=True, take_profit__isnull=True)

        for signal in active_signals:
            try:
                hit_result = self._check_tp_sl(signal, current_price)
                if not hit_result:
                    continue

                signal.status = "completed"
                signal.pnl_hit = hit_result["hit_type"]
                signal.actual_pnl = hit_result["pnl"]
                signal.exit_price = current_price
                signal.completed_at = timezone.now()
                signal.save()

                payload = {
                    "type": "signal_completed",
                    "signal": signal.as_dict(),
                    "hit_type": hit_result["hit_type"],
                    "pnl": hit_result["pnl"],
                    "current_price": current_price,
                }
                async_to_sync(broadcast)(payload)

                hit_signals.append(payload)
                logger.info(
                    "Signal %s hit %s at %s (pnl=%.2f%%)",
                    signal.symbol,
                    hit_result["hit_type"],
                    current_price,
                    hit_result["pnl"],
                )
            except Exception as exc:
                logger.error("Error checking signal %s: %s", signal.symbol, exc)

        return hit_signals

    def _check_tp_sl(self, signal: MarketSignal, current_price: float) -> Optional[Dict]:
        if not signal.stop_loss or not signal.take_profit:
            return None

        sl = signal.stop_loss
        tp = signal.take_profit
        entry = signal.price
        direction = signal.direction

        hit_type = None
        pnl = 0.0

        if direction == "Buy":
            if current_price >= tp:
                hit_type = "tp"
                pnl = (tp - entry) / get_pip_value(signal.symbol)
            elif current_price <= sl:
                hit_type = "sl"
                pnl = (sl - entry) / get_pip_value(signal.symbol)
        else:
            if current_price <= tp:
                hit_type = "tp"
                pnl = (entry - tp) / get_pip_value(signal.symbol)
            elif current_price >= sl:
                hit_type = "sl"
                pnl = (entry - sl) / get_pip_value(signal.symbol)

        if hit_type:
            return {"hit_type": hit_type, "pnl": round(pnl, 1)}

        return None


price_monitor = PriceMonitor()
