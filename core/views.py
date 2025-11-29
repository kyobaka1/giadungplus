# core/views.py
"""
Core app views.
"""

import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.cache import cache
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView

from core.sapo_client.client import SELENIUM_LOCK_KEY

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

