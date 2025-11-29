# kho/views/management.py
from django.shortcuts import render
from kho.utils import group_required
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@group_required("WarehouseManager")
def stats(request):
    """
    Thống kê kho:
    - Số đơn/ngày
    - Số đơn/nhân viên
    - Tỷ lệ lỗi kho...
    """
    # Get date range from request or default to today
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    today = datetime.now(tz_vn).date()
    
    date_from = request.GET.get("date_from", today.strftime("%Y-%m-%d"))
    date_to = request.GET.get("date_to", today.strftime("%Y-%m-%d"))
    
    # TODO: Query database for statistics
    # - Total orders packed
    # - Orders per employee
    # - Error rate
    # - Average packing time
    # - Top performing employees
    
    stats_data = {
        "total_orders": 0,
        "packed_orders": 0,
        "error_orders": 0,
        "error_rate": 0.0,
        "avg_packing_time": 0,
        "orders_by_employee": [],
        "orders_by_hour": [],
        "top_performers": [],
    }
    
    context = {
        "title": "Thống Kê Kho - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
        "date_from": date_from,
        "date_to": date_to,
        "stats": stats_data,
    }
    return render(request, "kho/management/stats.html", context)
