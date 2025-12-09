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

def has_shop_group(user, *shop_groups):
    """
    Kiểm tra user có thuộc một trong các shop groups được chỉ định.
    Shop groups: Shop_LTENG, Shop_PHALEDO, Shop_GIADUNGPLUS
    """
    if not user.is_authenticated:
        return False
    if shop_groups:
        return user.groups.filter(name__in=shop_groups).exists()
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

def marketing_permission_required(*allowed_groups, shop_groups=None):
    """
    Decorator cho marketing app:
    - MarketingManager/Staff: Có quyền vào tất cả các tính năng chung
    - MarketingIntern: Giới hạn quyền (tính sau vào từng tính năng)
    - Shop groups (Shop_LTENG, Shop_PHALEDO, Shop_GIADUNGPLUS): Chỉ ai có group này mới được vào tính năng của từng shop
    
    Args:
        allowed_groups: Các groups được phép truy cập (MarketingManager, MarketingStaff, MarketingIntern)
        shop_groups: Các shop groups cần kiểm tra (Shop_LTENG, Shop_PHALEDO, Shop_GIADUNGPLUS)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Admin luôn có quyền
            if request.user.is_superuser or request.user.groups.filter(name="Admin").exists():
                return view_func(request, *args, **kwargs)
            
            # Kiểm tra marketing groups
            has_marketing_access = False
            if allowed_groups:
                has_marketing_access = is_admin_or_group(request.user, *allowed_groups)
            
            # Kiểm tra shop groups nếu có yêu cầu
            has_shop_access = True  # Mặc định True nếu không yêu cầu shop groups
            if shop_groups:
                has_shop_access = has_shop_group(request.user, *shop_groups)
            
            if has_marketing_access and has_shop_access:
                return view_func(request, *args, **kwargs)
            else:
                return redirect('permission_denied')
        return wrapped_view
    return decorator

