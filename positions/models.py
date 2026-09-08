from django.db import models


class PaperPosition(models.Model):
    """A simulated position opened by the analysis engine when a signal
    clears the trade filters. Nothing here ever touches a real broker —
    this exists purely so the analysis window can show 'positions' the
    way a live TradeManager would, without placing real orders."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed_tp", "Closed — Take Profit"),
        ("closed_sl", "Closed — Stop Loss"),
        ("closed_manual", "Closed — Manual"),
    ]

    symbol = models.CharField(max_length=32, db_index=True)
    market_name = models.CharField(max_length=64)
    direction = models.CharField(max_length=8, choices=[("Buy", "Buy"), ("Sell", "Sell")])

    entry_price = models.FloatField()
    stop_loss = models.FloatField()
    take_profit = models.FloatField()
    volume = models.FloatField(help_text="Simulated lot size")
    risk_pct = models.FloatField(help_text="% of paper balance risked")

    signal_strength = models.FloatField(default=0)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="open")
    close_price = models.FloatField(null=True, blank=True)
    pnl = models.FloatField(null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"{self.symbol} {self.direction} {self.status} vol={self.volume}"

    def unrealized_pnl(self, current_price: float) -> float:
        contract_size = 100000
        direction_mult = 1 if self.direction == "Buy" else -1
        return direction_mult * (current_price - self.entry_price) * self.volume * contract_size

    def as_dict(self, current_price: float | None = None):
        pnl = self.pnl
        if self.status == "open" and current_price is not None:
            pnl = self.unrealized_pnl(current_price)
        return {
            "id": self.id,
            "symbol": self.symbol,
            "market_name": self.market_name,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "volume": self.volume,
            "risk_pct": round(self.risk_pct, 2),
            "status": self.status,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
