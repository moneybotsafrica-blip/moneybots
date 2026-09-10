import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# For Vercel deployment, use simple ASGI without Channels/WebSockets
# Vercel's Django deployment uses WSGI, so WebSocket functionality is not supported
if os.environ.get("VERCEL"):
    application = get_asgi_application()
else:
    # Local development: use Channels for WebSocket support
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter

    # django_asgi_app must be created before importing anything that touches models
    django_asgi_app = get_asgi_application()

    import analysis.routing  # noqa: E402

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": AuthMiddlewareStack(
                URLRouter(analysis.routing.websocket_urlpatterns)
            ),
        }
    )
