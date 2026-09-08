from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

from .context import base_context


def index(request):
    ctx = base_context(active_nav="dashboard")
    # Use a working symbol as default - frxEURUSD (EUR/USD) is confirmed to work with public API
    ctx["default_symbol"] = request.GET.get("symbol", "frxEURUSD")
    return render(request, "dashboard/index.html", ctx)
