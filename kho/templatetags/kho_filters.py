# kho/templatetags/kho_filters.py
"""
Custom template filters for kho module.
"""

from django import template

register = template.Library()


@register.filter
def format_currency(value):
    """
    Format số tiền theo định dạng K (nghìn), M (triệu), B (tỉ).
    
    Examples:
        1000 -> 1K
        1500000 -> 1.5M
        2500000000 -> 2.5B
    """
    try:
        num = float(value)
    except (ValueError, TypeError):
        return "0"
    
    if num == 0:
        return "0"
    
    abs_num = abs(num)
    sign = "-" if num < 0 else ""
    
    if abs_num >= 1_000_000_000:
        # Tỉ
        formatted = round(abs_num / 1_000_000_000, 1)
        # Loại bỏ .0 nếu là số nguyên
        if formatted == int(formatted):
            return f"{sign}{int(formatted)}B"
        return f"{sign}{formatted}B"
    elif abs_num >= 1_000_000:
        # Triệu
        formatted = round(abs_num / 1_000_000, 1)
        if formatted == int(formatted):
            return f"{sign}{int(formatted)}M"
        return f"{sign}{formatted}M"
    elif abs_num >= 1_000:
        # Nghìn
        formatted = round(abs_num / 1_000, 1)
        if formatted == int(formatted):
            return f"{sign}{int(formatted)}K"
        return f"{sign}{formatted}K"
    else:
        # Dưới 1000, hiển thị số nguyên
        return f"{sign}{int(abs_num)}"

