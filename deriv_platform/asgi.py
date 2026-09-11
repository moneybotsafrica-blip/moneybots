import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

django_asgi_app = get_asgi_application()

_migrated = False


async def _application(scope, receive, send):
    """Vercel (and Uvicorn) send lifespan before HTTP.

    Django's ASGIHandler only accepts scope type ``http`` and otherwise
    raises, which shows up as a 6ms GET / 500 on Route /django.
    """
    global _migrated
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
        return
    if not _migrated:
        from deriv_platform.vercel_runtime import apply_vercel_migrations

        apply_vercel_migrations()
        _migrated = True
    await django_asgi_app(scope, receive, send)


application = _application
app = application
