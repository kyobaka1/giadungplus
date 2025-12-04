from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json
from datetime import datetime

from kho.utils import admin_only
from ..services.config_service import SapoConfigService, ShopeeConfigService
from core.sapo_client import SapoClient
from products.services.shopee_init_service import ShopeeInitService
from core.services.notify import notify
from core.services.notification_delivery import NotificationDeliveryWorker


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
            "SAPO_LOGIN_USERNAME_FIELD": request.POST.get("SAPO_LOGIN_USERNAME_FIELD"),
            "SAPO_LOGIN_PASSWORD_FIELD": request.POST.get("SAPO_LOGIN_PASSWORD_FIELD"),
            "SAPO_LOGIN_BUTTON": request.POST.get("SAPO_LOGIN_BUTTON"),
            "SAPO_TMDT_STAFF_ID": request.POST.get("SAPO_TMDT_STAFF_ID"),
        }
        
        # Xử lý password: nếu không nhập mới, giữ nguyên password cũ
        new_password = request.POST.get("SAPO_PASSWORD", "").strip()
        if new_password:
            # Có nhập password mới
            data["SAPO_PASSWORD"] = new_password
        else:
            # Không nhập password mới, giữ nguyên password cũ
            current_config = SapoConfigService.get_config()
            data["SAPO_PASSWORD"] = current_config.get("SAPO_PASSWORD", "")
        
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

@admin_only
def init_data_view(request):
    """
    Trang Init data - Quản lý việc khởi tạo dữ liệu từ các nguồn
    """
    return render(request, 'settings/init_data.html')

@admin_only
@csrf_exempt
@require_http_methods(["POST"])
def init_shopee_products_api(request):
    """
    API endpoint để init Shopee products từ Sapo MP.
    
    POST /settings/init-data/init-shopee-products/
    
    Body (JSON):
    {
        "tenant_id": 1262,
        "connection_ids": "10925,134366,..." (optional, nếu không có sẽ lấy tất cả)
    }
    
    Returns:
    {
        "success": true/false,
        "total_products": 355,
        "processed": 100,
        "updated": 50,
        "errors": [...]
    }
    """
    try:
        data = json.loads(request.body)
        tenant_id = data.get("tenant_id")
        
        if not tenant_id:
            return JsonResponse({
                "success": False,
                "error": "tenant_id is required"
            }, status=400)
        
        connection_ids = data.get("connection_ids")
        
        # Initialize Sapo client
        sapo_client = SapoClient()
        
        # Initialize service
        init_service = ShopeeInitService(sapo_client)
        
        # Run init
        result = init_service.init_shopee_products(
            tenant_id=tenant_id,
            connection_ids=connection_ids
        )
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in init_shopee_products_api: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@admin_only
@require_http_methods(["GET", "POST"])
def push_notification_view(request):
    """
    Màn hình test hệ thống Notification (Notification Engine + Delivery).

    Cho phép:
    - Gửi notification theo group / department / shop / user_id.
    - Chọn action (show_popup, play_sound, badge_update, boss_popup).
    - Gửi ngay hoặc hẹn giờ (scheduled_time).
    - Gửi qua kênh in_app và/hoặc web_push.
    """
    if request.method == "POST":
        title = request.POST.get("title", "").strip() or "Thông báo"
        body = request.POST.get("body", "").strip()
        url = request.POST.get("url", "").strip() or "/"
        action = request.POST.get("action", "").strip() or "show_popup"
        sound = request.POST.get("sound", "").strip() or None
        count_raw = request.POST.get("count", "").strip()
        collapse_id = request.POST.get("collapse_id", "").strip() or None
        tag = request.POST.get("tag", "").strip() or None
        scheduled_time_raw = request.POST.get("scheduled_time", "").strip()
        event_type = request.POST.get("event_type", "").strip() or None

        # Target criteria
        groups_raw = request.POST.get("groups", "").strip()
        departments_raw = request.POST.get("departments", "").strip()
        shops_raw = request.POST.get("shops", "").strip()
        user_ids_raw = request.POST.get("user_ids", "").strip()

        # Channels
        send_in_app = request.POST.get("send_in_app") == "on"
        send_web_push = request.POST.get("send_web_push") == "on"

        extra_data_raw = request.POST.get("extra_data", "").strip()

        if not body:
            messages.error(request, "Nội dung (body) không được để trống.")
            return redirect("push_notification")

        # Parse JSON context nếu có
        extra_data = {}
        if extra_data_raw:
            try:
                extra_data = json.loads(extra_data_raw)
            except json.JSONDecodeError:
                messages.error(request, "Dữ liệu JSON bổ sung không hợp lệ.")
                return redirect("push_notification")

        # Thêm url vào context để service worker / frontend có thể dùng
        extra_data.setdefault("url", url)

        # Parse count
        count = None
        if count_raw:
            try:
                count = int(count_raw)
            except ValueError:
                messages.error(request, "Trường 'Count' phải là số nguyên.")
                return redirect("push_notification")

        # Parse scheduled_time (định dạng: YYYY-MM-DD HH:MM)
        scheduled_time = None
        if scheduled_time_raw:
            try:
                # Giả sử input theo giờ local, convert sang aware datetime
                naive_dt = datetime.strptime(scheduled_time_raw, "%Y-%m-%d %H:%M")
                scheduled_time = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            except ValueError:
                messages.error(request, "Thời gian hẹn giờ không hợp lệ. Định dạng: YYYY-MM-DD HH:MM")
                return redirect("push_notification")

        # Parse target criteria (comma-separated)
        def parse_csv(value: str):
            if not value:
                return None
            parts = [v.strip() for v in value.split(",") if v.strip()]
            return parts or None

        groups = parse_csv(groups_raw)
        departments = parse_csv(departments_raw)
        shops = parse_csv(shops_raw)

        user_ids = None
        if user_ids_raw:
            try:
                user_ids = [int(v.strip()) for v in user_ids_raw.split(",") if v.strip()]
            except ValueError:
                messages.error(request, "Trường 'User IDs' phải là danh sách số nguyên, phân cách bởi dấu phẩy.")
                return redirect("push_notification")

        # Channels list
        channels = []
        if send_in_app:
            channels.append("in_app")
        if send_web_push:
            channels.append("web_push")
        if not channels:
            # Nếu không chọn gì, mặc định gửi cả 2 kênh
            channels = ["in_app", "web_push"]

        # Gửi notification thông qua Notification Engine
        notification = notify.send(
            title=title,
            body=body,
            link=url,
            action=action,
            sound=sound,
            count=count,
            collapse_id=collapse_id,
            tag=tag,
            scheduled_time=scheduled_time,
            event_type=event_type,
            context=extra_data,
            groups=groups or "ALL",  # mặc định ALL nếu không chọn gì
            departments=departments,
            shops=shops,
            user_ids=user_ids,
            channels=channels,
        )

        # Nếu không hẹn giờ, xử lý gửi ngay để test
        if scheduled_time is None:
            result = NotificationDeliveryWorker.process_pending_deliveries(
                notification_id=notification.id
            )
            messages.success(
                request,
                (
                    f"Đã tạo notification #{notification.id}. "
                    f"Gửi ngay: processed={result['processed']}, "
                    f"success={result['success']}, failed={result['failed']}"
                ),
            )
        else:
            messages.success(
                request,
                (
                    f"Đã tạo scheduled notification #{notification.id} "
                    f"(sẽ gửi lúc {scheduled_time}). "
                    "Hãy đảm bảo cron job process_notifications đang chạy."
                ),
            )

        return redirect("push_notification")

    # GET
    return render(request, "settings/push_notification.html")