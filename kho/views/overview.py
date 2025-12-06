from django.shortcuts import render
from kho.utils import group_required
from kho.models import WarehousePackingSetting
from core.system_settings import get_connection_ids, SAPO_TMDT
from core.sapo_client import get_sapo_client

import logging
from requests import HTTPError

logger = logging.getLogger(__name__)

# Lưu ý: không tính sẵn connection_ids ở mức module để tránh phụ thuộc CWD / thời điểm import.
# Sẽ gọi get_connection_ids() bên trong view mỗi lần request.

@group_required("WarehouseManager")
def dashboard(request):
    """
    Màn hình tổng quan kho:
    - Đơn theo trạng thái (chuẩn bị, đang gói, đã gói...)
    - Đơn hoả tốc hôm nay
    - KPI theo ngày/tuần (sẽ gọi từ core.services sau)
    """
    current_kho = request.session.get("current_kho", "geleximco")
    location_id = 241737 if current_kho == "geleximco" else 548744
    
    # TODO: gọi service lấy KPI thực tế từ Sapo
    # Tạm thời dùng giá trị mẫu
    context = {
        "title": "Kho – Overview",
        "current_kho": current_kho,
        "kpi": {
            "orders_today": 0,  # TODO: Lấy từ Sapo Core API
            "orders_packed": 0,  # TODO: Lấy từ Sapo Core API
            "orders_express": 0,  # TODO: Lấy từ Marketplace API
            "orders_pickup": 0,  # TODO: Lấy từ Sapo Core API (packed nhưng chưa shipped)
        },
    }

    if 'kho' in request.GET:
        kho = request.GET.get("kho")
        # Chỉ cho phép 2 giá trị hợp lệ
        if kho in ["geleximco", "toky"]:
            request.session["current_kho"] = kho
        # Quay về trang trước, nếu không có thì về trang chủ
        next_url = request.META.get("HTTP_REFERER", "/")

    # New API - use repository directly
    sapo = get_sapo_client()

    # Đọc connection_ids theo runtime, tránh phụ thuộc vào CWD/server import time
    connection_ids = get_connection_ids()

    # Get marketplace orders (nếu đã cấu hình shop)
    mp_orders = None
    if connection_ids:
        try:
            mp_orders = sapo.marketplace.list_orders_raw(
                connection_ids=connection_ids,
                account_id=int(SAPO_TMDT.STAFF_ID),
                page=1,
                limit=250,
                sortBy="ISSUED_AT",
                orderBy="desc",
            )
        except HTTPError as e:
            # Log chi tiết để debug nhưng không làm trang overview bị crash
            logger.error(
                "Failed to load marketplace orders for overview: %s", e, exc_info=True
            )
    else:
        logger.warning(
            "No Shopee shops configured (empty connection_ids). "
            "Skipping marketplace orders on overview dashboard."
        )
    
    # Lấy cài đặt packing cho cả 2 kho
    packing_settings = {}
    for warehouse_code in ['KHO_HCM', 'KHO_HN']:
        setting = WarehousePackingSetting.get_setting_for_warehouse(warehouse_code)
        packing_settings[warehouse_code] = {
            'is_active': setting.is_active,
            'warehouse_display': setting.get_warehouse_code_display(),
        }
    
    context['packing_settings'] = packing_settings

    return render(request, "kho/overview.html", context)

