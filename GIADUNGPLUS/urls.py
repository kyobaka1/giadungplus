
# GIADUNGPLUS/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views   # ← thêm

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login / logout dùng chung cho toàn hệ thống
    path("login/",
         auth_views.LoginView.as_view(template_name="auth/login.html"),
         name="login"),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),

    path("kho/", include("kho.urls")),
    path("cskh/", include("cskh.urls")),
    path("marketing/", include("marketing.urls")),
    path("service/", include("service.urls")),
]
