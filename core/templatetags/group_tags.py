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
