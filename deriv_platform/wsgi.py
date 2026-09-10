import os
import logging

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# Configure logging for Vercel
if os.environ.get("VERCEL"):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.info("WSGI application starting on Vercel")

try:
    application = get_wsgi_application()
    # Vercel requires the app variable for WSGI applications
    app = application
    if os.environ.get("VERCEL"):
        logger.info("WSGI application loaded successfully")
except Exception as e:
    if os.environ.get("VERCEL"):
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to load WSGI application: {e}")
    raise
