import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

application = get_wsgi_application()
app = application

from deriv_platform.vercel_runtime import apply_vercel_migrations  # noqa: E402

apply_vercel_migrations()
