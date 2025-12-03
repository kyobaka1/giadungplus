# core/views.py
"""
Core app views.
"""

import logging
from typing import Any, Dict

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpRequest
from django.core.cache import cache
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.sapo_client.client import SELENIUM_LOCK_KEY
from .models import WebPushSubscription
from .serializers import WebPushSubscriptionSerializer

logger = logging.getLogger(__name__)


def custom_logout_view(request):
    """
    Custom logout view để xử lý cả GET và POST requests.
    """
    logout(request)
    return redirect('/login/')


class CustomLoginView(LoginView):
    """
    Custom login view để redirect về dashboard nếu user đã authenticated.
    """
    template_name = "auth/login.html"
    
    def dispatch(self, request, *args, **kwargs):
        # Nếu user đã đăng nhập, redirect về dashboard
        if request.user.is_authenticated:
            return redirect('/')
        # Gọi super để handle GET/POST requests bình thường
        return super().dispatch(request, *args, **kwargs)
    
    def get_success_url(self):
        # Sau khi login thành công, redirect về dashboard hoặc next parameter
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url:
            return next_url
        return '/'


@login_required
def dashboard_home(request):
    """
    Trang dashboard điều hướng sau khi login.
    Hiển thị grid các menu chính: Kho Hàng, CSKH, Quản trị, Cấu hình
    """
    if request.method != 'GET':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET'])
    
    context = {
        'title': 'Dashboard - Gia Dụng Plus',
    }
    return render(request, 'core/dashboard.html', context)


def selenium_loading_view(request):
    """
    Loading page hiển thị khi Selenium đang login.
    
    Page này sẽ polling status API và auto-redirect về URL gốc
    khi login hoàn tất.
    """
    logger.info("[SeleniumLoadingView] User waiting for Selenium login")
    
    # Lấy redirect URL từ session (đã được lưu bởi middleware)
    redirect_url = request.session.get('selenium_redirect_url', '/kho/')
    
    context = {
        'redirect_url': redirect_url,
    }
    
    return render(request, 'core/selenium_loading.html', context)


def permission_denied(request):
    """
    Trang thông báo không có quyền truy cập.
    """
    context = {
        'title': 'Không có quyền truy cập - Gia Dụng Plus',
    }
    return render(request, 'core/permission_denied.html', context)


def selenium_login_status_api(request):
    """
    API endpoint để check status của Selenium login.
    
    Returns:
        JSON: {
            "is_locked": true/false,
            "message": "..."
        }
    """
    is_locked = cache.get(SELENIUM_LOCK_KEY) is not None
    
    response_data = {
        'is_locked': is_locked,
        'message': 'Login in progress' if is_locked else 'Login completed'
    }
    
    logger.debug(f"[SeleniumStatusAPI] Lock status: {is_locked}")
    
    return JsonResponse(response_data)


@api_view(["POST"])
@authentication_classes([])  # Tắt SessionAuthentication để DRF không bắt CSRF
@permission_classes([AllowAny])
@csrf_exempt  # Bỏ kiểm tra CSRF ở middleware mức Django
def register_webpush_subscription(request: HttpRequest):
    """
    API endpoint: /api/push/register/

    Nhận thông tin subscription/token từ frontend và lưu vào DB.
    - Nếu endpoint đã tồn tại → update.
    - Nếu fcm_token trùng → update.
    - Ngược lại → tạo mới.

    Payload ví dụ:
    {
        "device_type": "android_web" | "ios_web" | "unknown",
        "endpoint": "...",
        "keys": {
            "p256dh": "...",
            "auth": "..."
        },
        "fcm_token": "..."
    }
    """

    serializer = WebPushSubscriptionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data: Dict[str, Any] = serializer.validated_data

    user = request.user if request.user.is_authenticated else None

    endpoint = data.get("endpoint")
    fcm_token = data.get("fcm_token")

    # Ưu tiên match theo endpoint (Web Push thuần)
    subscription = None
    created = False

    if endpoint:
        subscription, created = WebPushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": user,
                "device_type": data.get("device_type"),
                "p256dh": data.get("p256dh"),
                "auth": data.get("auth"),
                "fcm_token": fcm_token or "",
                "is_active": True,
            },
        )
    elif fcm_token:
        subscription, created = WebPushSubscription.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={
                "user": user,
                "device_type": data.get("device_type"),
                "p256dh": data.get("p256dh"),
                "auth": data.get("auth"),
                "endpoint": "",
                "is_active": True,
            },
        )

    if not subscription:
        return Response(
            {"detail": "Thiếu endpoint hoặc fcm_token."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    out = WebPushSubscriptionSerializer(subscription)
    return Response(
        {"created": created, "subscription": out.data},
        status=status.HTTP_200_OK,
    )

