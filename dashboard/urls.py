from django.urls import path
from django.shortcuts import redirect

from . import views
from analysis.views import live_signals_page

urlpatterns = [
    path("", views.index, name="dashboard_index"),
    path("signals/", live_signals_page, name="live_signals"),
]
