import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# django_asgi_app must be created before importing anything that touches models
django_asgi_app = get_asgi_application()

# Run migrations on first cold start for serverless environments —
# asgi.py is the entrypoint Vercel actually loads (WSGI_APPLICATION is
# ignored once ASGI_APPLICATION is also set), so this can't live in
# wsgi.py alone anymore.
# Check for DATABASE_URL to ensure migrations only run when DB is configured
if os.getenv("DATABASE_URL") and (os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")):
    try:
        from django.core.management import call_command
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        print("Running automatic database migrations...")
        call_command("migrate", "--noinput", verbosity=0)
        print("Migrations completed")
    except Exception as e:
        print(f"Migration notice: {e}")

import analysis.routing  # noqa: E402


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(analysis.routing.websocket_urlpatterns)
        ),
    }
)
