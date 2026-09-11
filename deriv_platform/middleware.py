import logging
import traceback

from django.http import HttpResponse

logger = logging.getLogger(__name__)


class VercelExceptionMiddleware:
    """Log the real traceback on Vercel. The default 500 page hides it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        tb = traceback.format_exc()
        logger.error("Unhandled exception on %s\n%s", request.path, tb)
        body = (
            "<h1>Server Error</h1><pre style='white-space:pre-wrap'>"
            f"{tb}</pre>"
        )
        return HttpResponse(body, status=500, content_type="text/html")
