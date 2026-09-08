from django.contrib import admin

from .models import PaperPosition


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    list_display = ("symbol", "direction", "status", "entry_price", "volume", "pnl", "opened_at")
    list_filter = ("status", "direction")
