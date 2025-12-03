# cskh/templatetags/ticket_filters.py
from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter
def time_ago(value):
    """
    Format datetime thành "X phút trước" hoặc "X giờ trước"
    """
    if not value:
        return ""
    
    now = timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    
    diff = now - value
    
    if diff < timedelta(minutes=1):
        return "Vừa xong"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} phút trước"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} giờ trước"
    elif diff < timedelta(days=7):
        days = int(diff.total_seconds() / 86400)
        return f"{days} ngày trước"
    else:
        # Nếu quá 7 ngày thì hiển thị ngày tháng
        return value.strftime("%d/%m/%Y")

