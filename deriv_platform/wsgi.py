import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# Vercel requires a module-level `app` or `application` assignment (not inside try/except).
application = get_wsgi_application()
app = application
