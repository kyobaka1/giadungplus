from django import template

register = template.Library()


@register.filter(name='has_group')
def has_group(user, group_name):
    """Check if user belongs to a specific group"""
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()


@register.simple_tag
def user_primary_group(user):
    """Get the user's primary (first) group name, or None if no groups"""
    if user.is_superuser:
        return 'superuser'
    group = user.groups.first()
    return group.name if group else None


@register.filter(name='position_tag_class')
def position_tag_class(position):
    """
    Map position (last_name) to CSS classes for tag styling.
    Returns tuple: (bg_color, text_color, border_color)
    """
    if not position:
        return "bg-gray-50 text-gray-600 border-gray-200"
    
    position_lower = position.lower().strip()
    
    # Admin/Quản trị
    if any(x in position_lower for x in ['quản trị', 'admin', 'administrator']):
        return "bg-purple-50 text-purple-700 border-purple-200"
    
    # Marketing
    if any(x in position_lower for x in ['marketing', 'marketer']):
        return "bg-pink-50 text-pink-700 border-pink-200"
    
    # CSKH
    if any(x in position_lower for x in ['cskh', 'chăm sóc', 'customer service', 'support']):
        return "bg-emerald-50 text-emerald-700 border-emerald-200"
    
    # Kho
    if any(x in position_lower for x in ['kho', 'warehouse', 'kho hàng']):
        return "bg-blue-50 text-blue-700 border-blue-200"
    
    # Sales
    if any(x in position_lower for x in ['sales', 'bán hàng', 'kinh doanh']):
        return "bg-green-50 text-green-700 border-green-200"
    
    # Manager
    if any(x in position_lower for x in ['manager', 'quản lý', 'trưởng']):
        return "bg-amber-50 text-amber-700 border-amber-200"
    
    # Default
    return "bg-gray-50 text-gray-600 border-gray-200"