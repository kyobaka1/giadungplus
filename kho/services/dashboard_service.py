# kho/services/dashboard_service.py
"""
Dashboard Service - Tính toán thống kê kho hàng từ SAPO orders.
"""

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from orders.services.sapo_service import SapoCoreOrderService, mo_rong_gon
from orders.services.order_builder import build_order_from_sapo

logger = logging.getLogger(__name__)

# Hệ số danh mục theo độ khó đóng gói
CATEGORY_MULTIPLIER = {
    "Thuỷ tinh": 1.3,
    "Tấm chắn dầu": 0.5,
}

# Mapping kho
SCOPE2KHO = {"geleximco": "HN", "toky": "HCM"}
LOCID2KHO = {241737: "HN", 548744: "HCM"}


def _cat_factor(cat_name: str) -> float:
    """Lấy hệ số nhân theo danh mục."""
    return CATEGORY_MULTIPLIER.get((cat_name or "").strip(), 1.0)


def _parse_packing_note(note: Optional[str]) -> Dict[str, Any]:
    """
    Parse packing note từ shipment note.
    Note format: JSON compressed với key mapping.
    """
    if not note or "{" not in note:
        return {}
    
    try:
        # Sử dụng mo_rong_gon từ sapo_service
        return mo_rong_gon(note)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_packing_data(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lấy thông tin packing từ order.
    Tương tự get_data_packing trong functions.py.
    """
    packing_data = {}
    
    fulfillments = order.get("fulfillments", [])
    if fulfillments:
        last_fulfillment = fulfillments[-1]
        shipment = last_fulfillment.get("shipment")
        if shipment:
            note = shipment.get("note")
            if note and "}" in note:
                packing_data = _parse_packing_note(note)
    
    # Set defaults
    if "packing_status" not in packing_data:
        packing_data["packing_status"] = 0
    if "nguoi_goi" not in packing_data:
        packing_data["nguoi_goi"] = "NO-SCAN"
    
    return packing_data


def _parse_time_packing(time_str: Optional[str], fallback_dt: datetime) -> datetime:
    """Parse time_packing string thành datetime."""
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    
    if not time_str:
        # Đảm bảo fallback_dt có timezone
        if fallback_dt.tzinfo:
            return fallback_dt
        else:
            return fallback_dt.replace(tzinfo=tz_vn)
    
    try:
        if len(time_str) <= 16:
            dt = datetime.strptime(time_str, "%H:%M %d-%m-%Y")
        else:
            dt = datetime.strptime(time_str, "%H:%M:%S %d-%m-%Y")
        
        # Đảm bảo có timezone
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=tz_vn)
        
        return dt
    except (ValueError, TypeError):
        # Đảm bảo fallback_dt có timezone
        if fallback_dt.tzinfo:
            return fallback_dt
        else:
            return fallback_dt.replace(tzinfo=tz_vn)


def _get_fast_deadline(created_time: datetime) -> datetime:
    """
    Tính deadline cho đơn hoả tốc.
    - Trước 18h: deadline 23:59:59 cùng ngày
    - Sau 18h: deadline 12:00 trưa ngày kế tiếp
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    created_local = created_time.astimezone(tz_vn) if created_time.tzinfo else created_time.replace(tzinfo=tz_vn)
    
    if 0 <= created_local.hour < 18:
        deadline = created_local.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        deadline = (created_local + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    
    # Nếu là Chủ nhật thì chuyển sang thứ 2
    if deadline.weekday() == 6:
        deadline = (deadline + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    
    return deadline


def _normalize_carrier(carrier_name: str) -> str:
    """Chuẩn hóa tên đơn vị vận chuyển."""
    if not carrier_name:
        return "SPX Express"
    
    carrier_lower = carrier_name.lower()
    hot_list = ["bedelivery", "grabexpress", "siêu tốc - 4 giờ", "ahamove", "spx instant"]
    congkenh = ["ghn - hàng cồng kềnh", "hàng cồng kềnh", "njv - hàng cồng kềnh"]
    spx = ["nhanh", "spx express"]
    
    if any(hot in carrier_lower for hot in hot_list):
        return "Hoả Tốc"
    elif any(ck in carrier_lower for ck in congkenh):
        return "Cồng Kềnh"
    elif any(s in carrier_lower for s in spx):
        return "SPX Express"
    else:
        return carrier_name


def calculate_dashboard_stats(
    orders: List[Dict[str, Any]],
    location_id: int,
    start_date: datetime,
    end_date: datetime,
    category_map: Optional[Dict[int, str]] = None
) -> Dict[str, Any]:
    """
    Tính toán thống kê dashboard từ danh sách orders.
    
    Args:
        orders: List orders từ SAPO API
        location_id: Location ID của kho (241737 hoặc 548744)
        start_date: Ngày bắt đầu (local time)
        end_date: Ngày kết thúc (local time)
        category_map: Dict mapping product_id -> category_name
        
    Returns:
        Dict chứa các thống kê
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)
    
    # Xác định scope (geleximco hoặc toky)
    kho_norm = LOCID2KHO.get(location_id, "HN")
    scope = "geleximco" if location_id == 241737 else "toky"
    
    # Containers để tổng hợp
    sum_data = {
        'sodonhang': 0,
        'doanhso': 0,
        'sosanpham': 0,
        'total_time': 0.0,
        'total_orders': 0,
        'total_time_xk': 0.0,
        'total_orders_xk': 0,
    }
    
    hourly_totals = defaultdict(int)
    per_user = {}
    per_category = {}
    carrier_summary = {}
    pending_deadlines = {
        'before_today': {'sodonhang': 0, 'doanhso': 0},
        'before_18': {'sodonhang': 0, 'doanhso': 0},
        'after_18': {'sodonhang': 0, 'doanhso': 0},
    }
    
    # Packing time range (local) - đảm bảo có timezone
    # start_date và end_date đã có timezone từ view, chỉ cần đảm bảo
    if not start_date.tzinfo:
        start_date = start_date.replace(tzinfo=tz_vn)
    if not end_date.tzinfo:
        end_date = end_date.replace(tzinfo=tz_vn)
    
    packing_start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    packing_end = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    for order in orders:
        # Lọc theo location_id
        if order.get('location_id') != location_id:
            continue
        
        # Lấy packing data
        packing_data = _get_packing_data(order)
        packing_status = packing_data.get("packing_status", 0)
        nguoi_goi = packing_data.get("nguoi_goi", "NO-SCAN")
        
        # Parse timestamps
        created_on_str = order.get('created_on')
        if not created_on_str:
            continue
        
        try:
            created_time = datetime.fromisoformat(created_on_str.replace('Z', '+00:00'))
            if created_time.tzinfo:
                created_time = created_time.astimezone(tz_vn)
            else:
                created_time = created_time.replace(tzinfo=tz_vn)
        except (ValueError, AttributeError):
            continue
        
        modified_on_str = order.get('modified_on', created_on_str)
        try:
            modified_time = datetime.fromisoformat(modified_on_str.replace('Z', '+00:00'))
            if modified_time.tzinfo:
                modified_time = modified_time.astimezone(tz_vn)
            else:
                modified_time = modified_time.replace(tzinfo=tz_vn)
        except (ValueError, AttributeError):
            modified_time = created_time
        
        # Parse time_packing
        time_packing_str = packing_data.get("time_packing")
        time_packing = _parse_time_packing(time_packing_str, modified_time)
        
        # Xử lý đơn chưa gói (packing_status < 4)
        if packing_status < 4:
            today_local = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_18 = today_local + timedelta(hours=18)
            
            if created_time.date() < today_local.date():
                category = 'before_today'
            elif today_local <= created_time <= cutoff_18:
                category = 'before_18'
            else:
                category = 'after_18'
            
            amount = int(order.get('total', 0))
            pending_deadlines[category]['sodonhang'] += 1
            pending_deadlines[category]['doanhso'] += amount
        
        # Chỉ tính đơn đã gói (packing_status >= 4) và time_packing trong khoảng
        if packing_status < 4:
            continue
        if not (packing_start <= time_packing <= packing_end):
            continue
        
        # Tính toán thống kê
        amount = int(order.get('total', 0))
        sum_data['sodonhang'] += 1
        sum_data['doanhso'] += amount
        
        # Thời gian gói
        time_diff = (time_packing - created_time).total_seconds()
        sum_data['total_time'] += time_diff / (24 * 3600)
        sum_data['total_orders'] += 1
        
        # Hourly totals
        hour = time_packing.hour
        hourly_totals[hour] += 1
        
        # Per user stats
        user_bucket = per_user.setdefault(nguoi_goi, {
            'total_money': 0,
            'total_quantity': 0,
            'total_order': 0,
            'cato': {},
        })
        
        # Line items
        order_total_qty = 0
        for line in order.get('order_line_items', []):
            qty = int(line.get('quantity', 0))
            line_amount = int(line.get('line_amount', 0))
            order_total_qty += qty
            
            # Category stats
            product_id = line.get('product_id')
            if category_map and product_id in category_map:
                cat = category_map[product_id]
                if cat:
                    user_bucket['cato'][cat] = user_bucket['cato'].get(cat, 0) + qty
                    
                    cat_bucket = per_category.setdefault(cat, {
                        'sosanpham': 0,
                        'doanhso': 0,
                    })
                    cat_bucket['sosanpham'] += qty
                    cat_bucket['doanhso'] += line_amount
        
        user_bucket['total_money'] += amount
        user_bucket['total_quantity'] += order_total_qty
        user_bucket['total_order'] += 1
        sum_data['sosanpham'] += order_total_qty
        
        # Carrier stats
        dvvc = packing_data.get("dvvc") or order.get('shipping_carrier_name', 'SPX Express')
        carrier = _normalize_carrier(dvvc)
        carrier_bucket = carrier_summary.setdefault(carrier, {
            'total': 0,
            'packed': 0,
            'handed_over': 0,
        })
        carrier_bucket['total'] += 1
        carrier_bucket['packed'] += 1
        
        # Xuất kho
        fulfillment_status = order.get('fulfillment_status')
        if fulfillment_status == "shipped":
            carrier_bucket['handed_over'] += 1
            
            fulfillments = order.get('fulfillments', [])
            if fulfillments:
                last_f = fulfillments[-1]
                shipped_on = last_f.get('shipped_on')
                if shipped_on:
                    try:
                        shipped_time = datetime.fromisoformat(shipped_on.replace('Z', '+00:00'))
                        if shipped_time.tzinfo:
                            shipped_time = shipped_time.astimezone(tz_vn)
                        else:
                            shipped_time = shipped_time.replace(tzinfo=tz_vn)
                        
                        time_diff_xk = (shipped_time - created_time).total_seconds()
                        sum_data['total_time_xk'] += time_diff_xk / (24 * 3600)
                        sum_data['total_orders_xk'] += 1
                    except (ValueError, AttributeError):
                        pass
    
    # Tính tổng pending
    pending_sum = {
        'sodonhang': sum(d['sodonhang'] for d in pending_deadlines.values()),
        'doanhso': sum(d['doanhso'] for d in pending_deadlines.values()),
    }
    
    # Sort users by revenue
    sorted_users = dict(sorted(per_user.items(), key=lambda x: x[1]['total_money'], reverse=True))
    
    # Sort categories by revenue
    sorted_categories = dict(sorted(per_category.items(), key=lambda x: x[1]['doanhso'], reverse=True))
    
    # Hourly data for chart
    hourly_data = [hourly_totals[h] for h in range(24)]
    hourly_categories = [str(h) for h in range(24)]
    
    return {
        'sum_data': sum_data,
        'pending_deadlines': pending_deadlines,
        'pending_sum': pending_sum,
        'per_user': sorted_users,
        'per_category': sorted_categories,
        'carrier_summary': carrier_summary,
        'hourly_data': hourly_data,
        'hourly_categories': hourly_categories,
        'scope': scope,
        'kho_norm': kho_norm,
    }

