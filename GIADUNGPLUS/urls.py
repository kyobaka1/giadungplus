
# GIADUNGPLUS/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views   # ← thêm
from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login / logout dùng chung cho toàn hệ thống
    path("login/",
         core_views.CustomLoginView.as_view(),
         name="login"),
    path(
        "logout/",
        core_views.custom_logout_view,
        name="logout",
    ),

    # Dashboard homepage - điều hướng sau khi login
    path("", core_views.dashboard_home, name='dashboard_home'),

    path("kho/", include("kho.urls")),
    path("cskh/", include("cskh.urls")),
    path("marketing/", include("marketing.urls")),
    path("chamcong/", include("chamcong.urls")),
    path("service/", include("service.urls")),
    path("products/", include("products.urls")),
    path("settings/", include("settings.urls")),
    path("core/", include("core.urls")),  # Selenium loading page

    # API Web Push Notification
    path(
        "api/push/register/",
        core_views.register_webpush_subscription,
        name="api_push_register",
    ),
    
    # API Notifications
    path("api/notifications/", core_views.list_notifications, name="api_notifications_list"),
    path("api/notifications/unread-count/", core_views.unread_notifications_count, name="api_notifications_unread_count"),
    path("api/notifications/<int:delivery_id>/mark-read/", core_views.mark_notification_read, name="api_notifications_mark_read"),
    path("api/notifications/mark-all-read/", core_views.mark_all_notifications_read, name="api_notifications_mark_all_read"),
]