from django.urls import path

from . import views

urlpatterns = [
    path("", views.calendar_page, name="news_calendar"),
    path("relevant/", views.relevant_news_api, name="relevant_news"),
    path("live-channels/", views.live_channels_api, name="live_channels"),
    path("live/", views.live_video_api, name="live_video"),
]
