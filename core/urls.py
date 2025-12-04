# core/urls.py
"""
Core app URL configuration.
"""

from django.urls import path
from . import views

urlpatterns = [
    path("permission-denied/", views.permission_denied, name="permission_denied"),
    path("selenium-loading/", views.selenium_loading_view, name="selenium_loading"),
    path("api/selenium-status/", views.selenium_login_status_api, name="selenium_status_api"),

    # Notification APIs
    path("api/notifications/", views.list_notifications, name="list_notifications"),
    path("api/notifications/unread-count/", views.unread_notifications_count, name="unread_count"),
    path("api/notifications/<int:delivery_id>/mark-read/", views.mark_notification_read, name="mark_notification_read"),
    path("api/notifications/mark-all-read/", views.mark_all_notifications_read, name="mark_all_read"),

    # Server logs (admin only)
    path("server-logs/", views.server_logs_view, name="server_logs_view"),
    path("api/server-logs/", views.server_logs_api, name="server_logs_api"),
]
