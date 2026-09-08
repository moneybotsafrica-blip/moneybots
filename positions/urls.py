from django.urls import path

from . import views

urlpatterns = [
    path("positions/", views.positions_list, name="positions_list"),
]
