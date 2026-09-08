from django.urls import path

from . import views

urlpatterns = [
    path("", views.stocks_page, name="stocks_page"),
    path("api/analyze-gaps/", views.analyze_gaps, name="analyze_gaps"),
    path("api/ticker/", views.get_stock_ticker, name="get_stock_ticker"),
]
