"""
WSGI config for GIADUNGPLUS project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Sử dụng production settings nếu biến môi trường không được set
# Hoặc có thể detect tự động dựa trên environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 
    os.environ.get('DJANGO_SETTINGS_MODULE', 'GIADUNGPLUS.settings_production'))

application = get_wsgi_application()
