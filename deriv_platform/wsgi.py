import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

app = get_wsgi_application()
application = app
