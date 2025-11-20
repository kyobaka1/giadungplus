# kho/urls.py
from django.urls import path
from . import views

app_name = "cskh"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("orders/", views.order_list, name="order_list"),
]
