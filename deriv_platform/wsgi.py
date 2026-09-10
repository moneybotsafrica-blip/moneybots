import os
import sys
import logging

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from django.core.wsgi import get_wsgi_application
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")
    
    logger.info("Initializing Django WSGI application...")
    
    app = get_wsgi_application()
    application = app
    
    # Vercel expects the WSGI application to be exported as "handler"
    handler = application
    
    logger.info("Django WSGI application initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Django WSGI application: {e}")
    import traceback
    traceback.print_exc()
    raise
