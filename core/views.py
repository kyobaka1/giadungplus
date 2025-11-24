# core/views.py
"""
Core app views.
"""

import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache

from core.sapo_client.client import SELENIUM_LOCK_KEY

logger = logging.getLogger(__name__)


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

