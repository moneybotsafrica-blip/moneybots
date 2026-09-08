from django.contrib import admin

from .models import MarketSignal


@admin.register(MarketSignal)
class MarketSignalAdmin(admin.ModelAdmin):
    list_display = ("symbol", "direction", "signal_strength", "setup_quality", "risk_level", "created_at")
    list_filter = ("direction", "market_type", "risk_level")
    search_fields = ("symbol", "market_name")
