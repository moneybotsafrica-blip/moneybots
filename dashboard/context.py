"""Shared context every template needs for the nav bar and
floating AI brain widget in base.html. Kept separate from views.py so other
apps' views (news, assistant) can reuse it without importing dashboard.views.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def base_context(active_nav: str = ""):
    try:
        from markets.catalog import AVAILABLE_MARKETS
        markets = AVAILABLE_MARKETS
    except Exception as e:
        logger.error(f"Error loading markets catalog: {e}")
        markets = {}
    
    try:
        return {
            "deriv_app_id": settings.DERIV_APP_ID,
            "deriv_api_token": "",  # Don't send API token to frontend for security
            "markets": markets,
            "ai_enabled": bool(settings.GROQ_API_KEY or settings.ANTHROPIC_API_KEY),
            "active_nav": active_nav,
        }
    except Exception as e:
        logger.error(f"Error creating base context: {e}")
        return {
            "deriv_app_id": "1089",
            "deriv_api_token": "",
            "markets": {},
            "ai_enabled": False,
            "active_nav": active_nav,
        }
