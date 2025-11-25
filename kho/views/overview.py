from django.shortcuts import render
from kho.utils import group_required
from core.system_settings import get_connection_ids, SAPO_TMDT
from core.sapo_client import get_sapo_client

connection_ids = get_connection_ids()

@group_required("CEO", "COO", "WarehouseManager")
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
    
    # Get marketplace orders
    mp_orders = sapo.marketplace.list_orders_raw(
        connection_ids=connection_ids,
        account_id=int(SAPO_TMDT.STAFF_ID),
        page=1,
        limit=50,
        sortBy="ISSUED_AT",
        orderBy="desc"
    )

    return render(request, "kho/overview.html", context)

