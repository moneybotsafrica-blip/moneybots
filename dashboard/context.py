"""Shared context every template needs for the nav bar and
floating AI brain widget in base.html. Kept separate from views.py so other
apps' views (news, assistant) can reuse it without importing dashboard.views.
"""
from django.conf import settings

from markets.catalog import AVAILABLE_MARKETS


def base_context(active_nav: str = ""):
    return {
        "deriv_app_id": settings.DERIV_APP_ID,
        "deriv_api_token": "",  # Don't send API token to frontend for security
        "markets": AVAILABLE_MARKETS,
        "ai_enabled": bool(settings.GROQ_API_KEY or settings.ANTHROPIC_API_KEY),
        "active_nav": active_nav,
    }
