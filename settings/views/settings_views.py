from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from kho.utils import admin_only
from ..services.config_service import SapoConfigService, ShopeeConfigService

@admin_only
def settings_dashboard(request):
    """
    Trang tổng quan Settings
    """
    return render(request, 'settings/dashboard.html')

@admin_only
@require_http_methods(["GET", "POST"])
def sapo_config_view(request):
    """
    Quản lý cấu hình Sapo (File-based)
    """
    if request.method == "POST":
        # Lấy dữ liệu từ form
        data = {
            "SAPO_MAIN_URL": request.POST.get("SAPO_MAIN_URL"),
            "SAPO_USERNAME": request.POST.get("SAPO_USERNAME"),
            "SAPO_PASSWORD": request.POST.get("SAPO_PASSWORD"),
            "SAPO_LOGIN_USERNAME_FIELD": request.POST.get("SAPO_LOGIN_USERNAME_FIELD"),
            "SAPO_LOGIN_PASSWORD_FIELD": request.POST.get("SAPO_LOGIN_PASSWORD_FIELD"),
            "SAPO_LOGIN_BUTTON": request.POST.get("SAPO_LOGIN_BUTTON"),
            "SAPO_TMDT_STAFF_ID": request.POST.get("SAPO_TMDT_STAFF_ID"),
        }
        
        # Lưu vào file
        SapoConfigService.save_config(data)
        messages.success(request, "Đã lưu cấu hình Sapo thành công!")
        return redirect('sapo_config')

    # GET: Load config hiện tại
    config = SapoConfigService.get_config()
    return render(request, 'settings/sapo_config.html', {'config': config})

@admin_only
def shopee_dashboard_view(request):
    """
    Danh sách các shop Shopee và trạng thái cookie
    """
    shops = ShopeeConfigService.get_shops()
    
    # Kiểm tra trạng thái cookie cho từng shop
    for shop in shops:
        cookie_content = ShopeeConfigService.get_cookie_content(shop['name'])
        shop['has_cookie'] = bool(cookie_content)
        
    return render(request, 'settings/shopee_shops.html', {'shops': shops})

@admin_only
@require_http_methods(["GET", "POST"])
def shopee_cookie_view(request, shop_name):
    """
    Chỉnh sửa cookie cho 1 shop
    """
    shop = ShopeeConfigService.get_shop_by_name(shop_name)
    if not shop:
        messages.error(request, f"Shop {shop_name} không tồn tại!")
        return redirect('shopee_settings')

    if request.method == "POST":
        cookie_content = request.POST.get("cookie_content")
        ShopeeConfigService.save_cookie_content(shop_name, cookie_content)
        messages.success(request, f"Đã lưu cookie cho shop {shop_name}!")
        return redirect('shopee_settings')

    # GET: Load cookie hiện tại
    current_cookie = ShopeeConfigService.get_cookie_content(shop_name)
    return render(request, 'settings/shopee_cookie_edit.html', {
        'shop': shop,
        'current_cookie': current_cookie
    })

def test_view(request):
    """
    Trang test header template
    """
    return render(request, 'settings/test.html')