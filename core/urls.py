# core/urls.py
"""
Core app URL configuration.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('permission-denied/', views.permission_denied, name='permission_denied'),
    path('selenium-loading/', views.selenium_loading_view, name='selenium_loading'),
    path('api/selenium-status/', views.selenium_login_status_api, name='selenium_status_api'),
]
