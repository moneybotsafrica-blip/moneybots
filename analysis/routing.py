from django.urls import re_path

from .consumers import AnalysisConsumer

websocket_urlpatterns = [
    re_path(r"^ws/analysis/$", AnalysisConsumer.as_asgi()),
]
