# core/middleware/selenium_login_middleware.py
"""
Middleware to handle SeleniumLoginInProgressException.

When a view raises SeleniumLoginInProgressException, this middleware
will save the original URL and redirect to a loading page.
"""

import logging
from django.shortcuts import redirect
from django.urls import reverse

from core.sapo_client.exceptions import SeleniumLoginInProgressException

logger = logging.getLogger(__name__)


class SeleniumLoginMiddleware:
    """
    Middleware để catch SeleniumLoginInProgressException và redirect
    người dùng đến loading page.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        """
        Catch SeleniumLoginInProgressException và redirect tới loading page.
        """
        if isinstance(exception, SeleniumLoginInProgressException):
            logger.info(f"[SeleniumLoginMiddleware] Caught exception, redirecting to loading page")
            
            # Lưu original URL vào session để redirect lại sau khi login xong
            original_url = request.get_full_path()
            request.session['selenium_redirect_url'] = original_url
            request.session.save()  # Explicitly save session
            
            logger.debug(f"[SeleniumLoginMiddleware] Saved redirect URL: {original_url}")
            
            # Redirect đến loading page
            return redirect('selenium_loading')
        
        # Không phải exception của mình, return None để Django xử lý bình thường
        return None

