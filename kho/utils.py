from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from functools import wraps

def is_admin_or_group(user, *group_names):
    """
    Kiểm tra user có phải là Admin (superuser hoặc group Admin) hoặc thuộc một trong các groups.
    """
    if not user.is_authenticated:
        return False
    # Admin = superuser hoặc có group "Admin"
    if user.is_superuser or user.groups.filter(name="Admin").exists():
        return True
    # Kiểm tra các groups khác
    if group_names:
        return user.groups.filter(name__in=group_names).exists()
    return False

def group_required(*group_names):
    """
    Decorator yêu cầu user phải là Admin hoặc thuộc một trong các groups được chỉ định.
    Nếu không có quyền, redirect về trang thông báo.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if is_admin_or_group(request.user, *group_names):
                return view_func(request, *args, **kwargs)
            else:
                # Redirect về trang thông báo không có quyền
                return redirect('permission_denied')
        return wrapped_view
    return decorator

def admin_only(view_func):
    """
    Decorator chỉ cho phép Admin (superuser hoặc group Admin) truy cập.
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if is_admin_or_group(request.user, "Admin"):
            return view_func(request, *args, **kwargs)
        else:
            return redirect('permission_denied')
    return wrapped_view
