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


def _get_fast_deadline(created_time: datetime, channel: Optional[str] = None) -> datetime:
    """
    Tính deadline bàn giao cho đơn vị vận chuyển theo quy định Shopee.
    
    Theo tài liệu: https://banhang.shopee.vn/edu/article/21365
    - Đơn phát sinh từ 0:00 - 17:59: Hạn bàn giao trước 23:59 cùng ngày
    - Đơn phát sinh từ 18:00 - 23:59: Hạn bàn giao trước 11:59 trưa ngày kế tiếp
    
    Args:
        created_time: Thời gian tạo đơn (datetime với timezone)
        channel: Channel của đơn (Shopee, TikTok, etc.) - optional
        
    Returns:
        Deadline datetime
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    created_local = created_time.astimezone(tz_vn) if created_time.tzinfo else created_time.replace(tzinfo=tz_vn)
    
    # Quy định deadline theo Shopee
    if 0 <= created_local.hour < 18:
        # Đơn phát sinh từ 0:00 - 17:59: deadline 23:59 cùng ngày
        deadline = created_local.replace(hour=23, minute=59, second=0, microsecond=0)
    else:
        # Đơn phát sinh từ 18:00 - 23:59: deadline 11:59 trưa ngày kế tiếp
        deadline = (created_local + timedelta(days=1)).replace(hour=11, minute=59, second=0, microsecond=0)
    
    # Nếu deadline rơi vào Chủ nhật thì chuyển sang thứ 2, 11:59
    if deadline.weekday() == 6:
        deadline = (deadline + timedelta(days=1)).replace(hour=11, minute=59, second=0, microsecond=0)
    
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


def _calculate_working_hours(packing_times: List[datetime], tz_vn: ZoneInfo) -> float:
    """
    Tính giờ làm việc từ danh sách thời gian gói hàng.
    
    Logic:
    - Bắt đầu từ 8:00 sáng (nếu đơn đầu < 8h thì tính từ 8h)
    - Trưa nghỉ từ 12h đến 14h
    - Chiều nghỉ từ 18h
    - Nếu trong giờ nghỉ mà gói > 15 đơn/30 phút thì tính thêm giờ
    - Làm tròn về 0.1 giờ (1.1, 1.2, ...)
    
    Args:
        packing_times: Danh sách thời gian gói hàng (đã có timezone)
        tz_vn: Timezone Việt Nam
        
    Returns:
        Số giờ làm việc (float, làm tròn 1 chữ số thập phân)
    """
    if not packing_times:
        return 0.0
    
    # Sắp xếp theo thời gian
    sorted_times = sorted(packing_times)
    first_time = sorted_times[0]
    last_time = sorted_times[-1]
    
    # Bắt đầu từ 8:00 sáng (nếu đơn đầu < 8h thì tính từ 8h)
    work_start_8h = first_time.replace(hour=8, minute=0, second=0, microsecond=0)
    if first_time < work_start_8h:
        work_start = work_start_8h  # Tính từ 8h nếu đơn đầu < 8h
    else:
        work_start = first_time  # Tính từ đơn đầu nếu >= 8h
    
    # Kết thúc là đơn cuối cùng
    work_end = last_time
    
    # Tính tổng thời gian (giờ)
    total_hours = (work_end - work_start).total_seconds() / 3600.0
    
    # Trừ giờ nghỉ trưa (12h-14h) nếu có
    lunch_start = work_start.replace(hour=12, minute=0, second=0, microsecond=0)
    lunch_end = work_start.replace(hour=14, minute=0, second=0, microsecond=0)
    
    # Kiểm tra xem có gói hàng trong giờ nghỉ trưa không
    lunch_orders = [t for t in sorted_times if lunch_start <= t < lunch_end]
    if lunch_orders:
        # Kiểm tra xem có > 15 đơn trong 30 phút không
        lunch_orders_sorted = sorted(lunch_orders)
        for i in range(len(lunch_orders_sorted) - 1):
            time_diff = (lunch_orders_sorted[i+1] - lunch_orders_sorted[i]).total_seconds() / 60.0  # phút
            if time_diff <= 30 and len(lunch_orders_sorted) > 15:
                # Tính thêm giờ từ 12h đến đơn cuối cùng trong giờ nghỉ
                last_lunch_order = lunch_orders_sorted[-1]
                lunch_overtime = (last_lunch_order - lunch_start).total_seconds() / 3600.0
                total_hours += lunch_overtime
                break
        else:
            # Không có > 15 đơn/30 phút -> trừ 2 giờ nghỉ trưa
            if work_start < lunch_end and work_end > lunch_start:
                lunch_overlap = min(work_end, lunch_end) - max(work_start, lunch_start)
                total_hours -= lunch_overlap.total_seconds() / 3600.0
    else:
        # Không có đơn trong giờ nghỉ trưa -> trừ 2 giờ
        if work_start < lunch_end and work_end > lunch_start:
            lunch_overlap = min(work_end, lunch_end) - max(work_start, lunch_start)
            total_hours -= lunch_overlap.total_seconds() / 3600.0
    
    # Kiểm tra giờ nghỉ chiều (18h)
    evening_start = work_start.replace(hour=18, minute=0, second=0, microsecond=0)
    if work_end > evening_start:
        # Kiểm tra xem có gói hàng sau 18h không
        evening_orders = [t for t in sorted_times if t >= evening_start]
        if evening_orders:
            # Kiểm tra xem có > 15 đơn trong 30 phút không
            evening_orders_sorted = sorted(evening_orders)
            for i in range(len(evening_orders_sorted) - 1):
                time_diff = (evening_orders_sorted[i+1] - evening_orders_sorted[i]).total_seconds() / 60.0  # phút
                if time_diff <= 30 and len(evening_orders_sorted) > 15:
                    # Tính thêm giờ từ 18h đến đơn cuối cùng
                    last_evening_order = evening_orders_sorted[-1]
                    evening_overtime = (last_evening_order - evening_start).total_seconds() / 3600.0
                    total_hours += evening_overtime
                    break
            else:
                # Không có > 15 đơn/30 phút -> không tính giờ sau 18h
                if work_start < evening_start:
                    total_hours -= (work_end - evening_start).total_seconds() / 3600.0
        else:
            # Không có đơn sau 18h -> không tính giờ sau 18h
            if work_start < evening_start:
                total_hours -= (work_end - evening_start).total_seconds() / 3600.0
    
    # Làm tròn về 0.1 giờ (1.1, 1.2, ...)
    return round(total_hours, 1)


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
    
    # Thống kê doanh số từ shipment note (lọc trước 2 ngày và sau 2 ngày)
    doanhso_shipment = 0  # Doanh số từ shipment note
    
    hourly_totals = defaultdict(int)
    per_user = {}
    per_category = {}
    carrier_summary = {}
    pending_deadlines = {
        'before_today': {'sodonhang': 0, 'doanhso': 0},
        'before_18': {'sodonhang': 0, 'doanhso': 0},
        'after_18': {'sodonhang': 0, 'doanhso': 0},
    }
    
    # Thống kê deadline mới: Giao trước 12H, 24H, Trưa mai
    deadline_stats = {
        'before_12h': {'sodonhang': 0, 'doanhso': 0},
        'before_24h': {'sodonhang': 0, 'doanhso': 0},
        'trua_mai': {'sodonhang': 0, 'doanhso': 0},
    }
    
    # Đếm đơn chưa gói và đã gói
    don_chua_goi = {'sodonhang': 0, 'doanhso': 0}
    don_da_goi = {'sodonhang': 0, 'doanhso': 0}
    
    # Packing time range (local) - đảm bảo có timezone
    # start_date và end_date đã có timezone từ view, chỉ cần đảm bảo
    if not start_date.tzinfo:
        start_date = start_date.replace(tzinfo=tz_vn)
    if not end_date.tzinfo:
        end_date = end_date.replace(tzinfo=tz_vn)
    
    # Thời gian gói hàng (cho cả tổng đơn đã gói và doanh số)
    # Cả hai đều lấy từ shipment note với packing_status >= 4 và time_packing trong khoảng thời gian đã lọc
    packing_start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    packing_end = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Set để lưu danh sách người gói trong hôm nay (cho tính hiệu suất)
    nguoi_goi_set = set()
    
    # Debug: Đếm orders theo location_id
    orders_by_location = defaultdict(int)
    orders_processed = 0
    orders_packed = 0
    
    for order in orders:
        order_location = order.get('location_id')
        orders_by_location[order_location] += 1
        
        # Lọc theo location_id
        if order_location != location_id:
            continue
        
        orders_processed += 1
        
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
            amount = int(order.get('total', 0))
            don_chua_goi['sodonhang'] += 1
            don_chua_goi['doanhso'] += amount
            
            # Tính deadline cho đơn chưa gói (theo quy định Shopee/TikTok)
            channel = order.get('channel', '') or ''
            deadline = _get_fast_deadline(created_time, channel)
            
            # Tính các mốc thời gian để phân loại
            today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
            today_noon = now_vn.replace(hour=12, minute=0, second=0, microsecond=0)
            today_end = now_vn.replace(hour=23, minute=59, second=59, microsecond=0)
            tomorrow_noon = (now_vn + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
            
            # Phân loại deadline theo thứ tự ưu tiên:
            # 1. Trưa mai: deadline là 12:00:00 ngày kế tiếp
            # Kiểm tra nếu deadline là 12:00 trưa ngày kế tiếp (hoặc 11:59 trưa ngày kế tiếp - theo quy định Shopee)
            tomorrow_date = (now_vn + timedelta(days=1)).date()
            is_trua_mai = (
                deadline.date() == tomorrow_date and
                ((deadline.hour == 12 and deadline.minute == 0) or 
                 (deadline.hour == 11 and deadline.minute == 59))  # Chấp nhận cả 11:59 và 12:00
            )
            
            if is_trua_mai:
                # Deadline là trưa mai (12:00 trưa ngày kế tiếp)
                deadline_stats['trua_mai']['sodonhang'] += 1
                deadline_stats['trua_mai']['doanhso'] += amount
            # 2. Giao trước 12H: deadline <= 12:00:00 hôm nay
            elif deadline.date() == now_vn.date() and deadline <= today_noon:
                deadline_stats['before_12h']['sodonhang'] += 1
                deadline_stats['before_12h']['doanhso'] += amount
            # 3. Giao trước 24H: deadline <= 23:59:59 hôm nay (nhưng không phải trưa mai và không phải trước 12H)
            elif deadline.date() == now_vn.date() and deadline <= today_end:
                deadline_stats['before_24h']['sodonhang'] += 1
                deadline_stats['before_24h']['doanhso'] += amount
            # 4. Deadline là ngày khác (quá hôm nay hoặc quá ngày mai) - không phân loại vào 3 nhóm trên
            else:
                # Deadline không phải hôm nay hoặc trưa mai - có thể log để debug
                if orders_processed <= 5:  # Chỉ log 5 đơn đầu tiên
                    logger.debug(f"[Dashboard] Order {order.get('id')} deadline không khớp: deadline={deadline.strftime('%Y-%m-%d %H:%M')}, today={now_vn.strftime('%Y-%m-%d %H:%M')}, created={created_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Giữ lại logic cũ cho pending_deadlines
            today_local = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_18 = today_local + timedelta(hours=18)
            
            if created_time.date() < today_local.date():
                category = 'before_today'
            elif today_local <= created_time <= cutoff_18:
                category = 'before_18'
            else:
                category = 'after_18'
            
            pending_deadlines[category]['sodonhang'] += 1
            pending_deadlines[category]['doanhso'] += amount
        
        # Chỉ tính đơn đã gói (packing_status >= 4) và time_packing trong khoảng thời gian đã lọc
        # Cả tổng đơn đã gói và doanh số đều lấy từ shipment note với cùng điều kiện
        if packing_status < 4:
            continue
        if not (packing_start <= time_packing <= packing_end):
            continue
        
        orders_packed += 1
        
        # Tính toán thống kê cho tổng đơn đã gói và doanh số (cùng điều kiện)
        amount = int(order.get('total', 0))
        sum_data['sodonhang'] += 1
        doanhso_shipment += amount  # Doanh số từ shipment note
        sum_data['doanhso'] += amount  # Giữ lại để tương thích
        
        # Đếm đơn đã gói
        don_da_goi['sodonhang'] += 1
        don_da_goi['doanhso'] += amount
        
        # Lưu người gói để tính hiệu suất
        if nguoi_goi and nguoi_goi != "NO-SCAN":
            nguoi_goi_set.add(nguoi_goi)
        
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
            'packing_times': [],  # Lưu thời gian gói hàng để tính giờ làm
        })
        
        # Lưu thời gian gói hàng
        user_bucket['packing_times'].append(time_packing)
        
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
    
    # Log debug info
    logger.info(f"[Dashboard] Location filter: location_id={location_id}, orders_by_location={dict(orders_by_location)}")
    logger.info(f"[Dashboard] Orders processed: {orders_processed}, orders_packed: {orders_packed}")
    logger.info(f"[Dashboard] Stats: sodonhang={sum_data['sodonhang']}, doanhso_shipment={doanhso_shipment}, sosanpham={sum_data['sosanpham']}")
    
    # Tính tổng pending
    pending_sum = {
        'sodonhang': sum(d['sodonhang'] for d in pending_deadlines.values()),
        'doanhso': sum(d['doanhso'] for d in pending_deadlines.values()),
    }
    
    # Tính tổng số đơn cần xử lý hôm nay
    # Đơn chưa gói có deadline hôm nay (Giao trước 12H + Giao trước 24H, không bao gồm Trưa mai)
    don_chua_goi_hom_nay = (
        deadline_stats['before_12h']['sodonhang'] + 
        deadline_stats['before_24h']['sodonhang']
    )
    
    # Tổng đơn cần xử lý hôm nay = Đã gói + Chưa gói
    # Đã gói: đơn đã gói trong khoảng thời gian lọc
    # Chưa gói: đơn chưa gói có deadline hôm nay
    total_don_can_xu_ly_hom_nay = don_da_goi['sodonhang'] + don_chua_goi_hom_nay
    
    # Tính phần trăm: Tỉ lệ % = đã gói / tổng
    if total_don_can_xu_ly_hom_nay > 0:
        # Phần trăm đơn đã gói = đã gói / tổng
        don_da_goi['percent'] = round((don_da_goi['sodonhang'] / total_don_can_xu_ly_hom_nay) * 100, 2)
        # Phần trăm đơn chưa gói = chưa gói / tổng
        don_chua_goi['percent'] = round((don_chua_goi_hom_nay / total_don_can_xu_ly_hom_nay) * 100, 2)
    else:
        don_chua_goi['percent'] = 0
        don_da_goi['percent'] = 0
    
    # Lưu tổng số đơn cần xử lý hôm nay vào don_chua_goi để template sử dụng
    don_chua_goi['total_don_can_xu_ly_hom_nay'] = total_don_can_xu_ly_hom_nay
    # Lưu số đơn chưa gói có deadline hôm nay
    don_chua_goi['sodonhang_hom_nay'] = don_chua_goi_hom_nay
    
    # Tính hiệu suất làm việc: doanh số / (số người gói * 8h)
    so_nguoi_goi = len(nguoi_goi_set)
    tong_gio_lam = so_nguoi_goi * 8  # 8h * số người gói
    hieu_suat_doanhso_h = doanhso_shipment / tong_gio_lam if tong_gio_lam > 0 else 0
    hieu_suat_don_h = sum_data['sodonhang'] / tong_gio_lam if tong_gio_lam > 0 else 0
    
    # Lấy thống kê ticket từ CSKH
    try:
        from cskh.models import Ticket
        from django.db.models import Q
        
        # Tổng ticket
        total_tickets = Ticket.objects.count()
        
        # Chưa xử lý: status != 'resolved' và != 'closed'
        unprocessed_tickets = Ticket.objects.filter(
            ~Q(ticket_status__in=['resolved', 'closed'])
        ).count()
    except Exception as e:
        logger.warning(f"[Dashboard] Error getting ticket stats: {e}")
        total_tickets = 0
        unprocessed_tickets = 0
    
    # Tính giờ làm và hiệu suất cho từng người
    # Tìm username từ User model
    try:
        from django.contrib.auth.models import User
        user_map = {}  # Map (last_name, first_name) -> username
        for user in User.objects.all():
            if user.last_name and user.first_name:
                key = (user.last_name, user.first_name)
                user_map[key] = user.username
    except Exception as e:
        logger.warning(f"[Dashboard] Error loading user map: {e}")
        user_map = {}
    
    for user_name, user_data in per_user.items():
        # Parse tên nhân viên: "KHO_HN: Hương Giang" -> kho="KHO_HN", tên="Hương Giang"
        if ':' in user_name:
            parts = user_name.split(':', 1)
            kho_name = parts[0].strip()
            real_name = parts[1].strip()
        else:
            kho_name = None
            real_name = user_name
        
        user_data['kho_name'] = kho_name
        user_data['real_name'] = real_name
        
        # Tìm username từ User model
        username = None
        if kho_name and real_name:
            key = (kho_name, real_name)
            username = user_map.get(key)
        
        user_data['username'] = username or 'chuaco'  # Default avatar nếu không tìm thấy
        
        # Tính giờ làm
        packing_times = user_data.get('packing_times', [])
        working_hours = _calculate_working_hours(packing_times, tz_vn)
        user_data['working_hours'] = working_hours
        
        # Tính hiệu suất (doanh số/giờ)
        if working_hours > 0:
            user_data['efficiency'] = round(user_data['total_money'] / working_hours, 0)
        else:
            user_data['efficiency'] = 0
        
        # Tính xu hướng gói TOP3 categories
        cato = user_data.get('cato', {})
        if cato:
            # Tính tổng số sản phẩm để tính phần trăm
            total_cato_qty = sum(cato.values())
            # Sắp xếp theo số lượng giảm dần
            sorted_cato = sorted(cato.items(), key=lambda x: x[1], reverse=True)
            # Lấy TOP3
            top3_cato = []
            for cat_name, qty in sorted_cato[:3]:
                percent = round((qty / total_cato_qty) * 100, 0) if total_cato_qty > 0 else 0
                top3_cato.append({
                    'name': cat_name,
                    'percent': int(percent),
                    'quantity': qty
                })
            user_data['top3_categories'] = top3_cato
        else:
            user_data['top3_categories'] = []
        
        # Xóa packing_times khỏi output (không cần thiết)
        if 'packing_times' in user_data:
            del user_data['packing_times']
    
    # Sort users by revenue
    sorted_users = dict(sorted(per_user.items(), key=lambda x: x[1]['total_money'], reverse=True))
    
    # Tìm TOP 1 doanh số và TOP 1 hiệu suất
    top1_doanhso_user = None
    top1_hieu_suat_user = None
    max_doanhso = 0
    max_hieu_suat = 0
    
    for user_name, user_data in sorted_users.items():
        total_money = user_data.get('total_money', 0) or 0
        efficiency = user_data.get('efficiency', 0) or 0
        
        if total_money > max_doanhso:
            max_doanhso = total_money
            top1_doanhso_user = user_name
        
        if efficiency > max_hieu_suat:
            max_hieu_suat = efficiency
            top1_hieu_suat_user = user_name
    
    # Sort categories by revenue
    sorted_categories = dict(sorted(per_category.items(), key=lambda x: x[1]['doanhso'], reverse=True))
    
    # Tính tổng doanh số categories để tính phần trăm
    total_category_doanhso = sum(cat_data['doanhso'] for cat_data in per_category.values()) or 1
    
    # Thêm phần trăm vào mỗi category
    for cat_name, cat_data in sorted_categories.items():
        cat_data['percent'] = round((cat_data['doanhso'] / total_category_doanhso) * 100, 2) if total_category_doanhso > 0 else 0
    
    # Hourly data for chart
    hourly_data = [hourly_totals[h] for h in range(24)]
    hourly_categories = [str(h) for h in range(24)]
    
    # Category data for chart (biểu đồ thanh 100%)
    category_chart_data = {
        'labels': list(sorted_categories.keys())[:10],  # Top 10 categories
        'values': [sorted_categories[cat]['doanhso'] for cat in list(sorted_categories.keys())[:10]],
        'percentages': [sorted_categories[cat]['percent'] for cat in list(sorted_categories.keys())[:10]],
    }
    
    # Tính tỷ lệ sản phẩm/đơn
    ty_le_sp_don = sum_data['sosanpham'] / sum_data['sodonhang'] if sum_data['sodonhang'] > 0 else 0
    
    # Tính toán giao đúng hạn (cho đơn đã gói trong khoảng thời gian lọc)
    delivery_stats = {
        'not_shipped_late': {'sodonhang': 0, 'doanhso': 0},  # Chưa giao, trễ ⚠️
        'shipped_late': {'sodonhang': 0, 'doanhso': 0},  # Đã giao, trễ ⏰
        'shipped_on_time': {'sodonhang': 0, 'doanhso': 0},  # Giao đúng hạn ✅
    }
    
    # Tính lại cho tất cả đơn đã gói (packing_status >= 4) trong khoảng thời gian lọc
    for order in orders:
        if order.get('location_id') != location_id:
            continue
        
        packing_data = _get_packing_data(order)
        packing_status = int(packing_data.get("packing_status", 0))
        
        # Chỉ tính đơn đã gói (packing_status >= 4)
        if packing_status < 4:
            continue
        
        # Kiểm tra time_packing có trong khoảng thời gian lọc không
        time_packing_str = packing_data.get("time_packing")
        if not time_packing_str:
            continue
        
        try:
            created_on_str = order.get('created_on', '')
            if not created_on_str:
                continue
            
            created_time = datetime.fromisoformat(created_on_str.replace('Z', '+00:00'))
            if created_time.tzinfo:
                created_time = created_time.astimezone(tz_vn)
            else:
                created_time = created_time.replace(tzinfo=tz_vn)
            
            modified_on_str = order.get('modified_on', created_on_str)
            try:
                modified_time = datetime.fromisoformat(modified_on_str.replace('Z', '+00:00'))
                if modified_time.tzinfo:
                    modified_time = modified_time.astimezone(tz_vn)
                else:
                    modified_time = modified_time.replace(tzinfo=tz_vn)
            except (ValueError, AttributeError):
                modified_time = created_time
            
            time_packing = _parse_time_packing(time_packing_str, modified_time)
            
            # Kiểm tra time_packing có trong khoảng thời gian lọc không
            if time_packing < start_date or time_packing > end_date:
                continue
            
            # Tính deadline
            channel = order.get('channel', '') or ''
            deadline = _get_fast_deadline(created_time, channel)
            
            # Kiểm tra fulfillment_status và shipped_on
            fulfillment_status = order.get('fulfillment_status')
            amount = int(order.get('total', 0))
            
            if fulfillment_status == "shipped":
                # Đã giao - kiểm tra shipped_on
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
                            
                            # So sánh shipped_time với deadline
                            if shipped_time <= deadline:
                                # Giao đúng hạn ✅
                                delivery_stats['shipped_on_time']['sodonhang'] += 1
                                delivery_stats['shipped_on_time']['doanhso'] += amount
                            else:
                                # Đã giao, trễ ⏰
                                delivery_stats['shipped_late']['sodonhang'] += 1
                                delivery_stats['shipped_late']['doanhso'] += amount
                        except (ValueError, AttributeError):
                            # Không parse được shipped_on - bỏ qua
                            pass
                    else:
                        # Không có shipped_on - bỏ qua
                        pass
                else:
                    # Không có fulfillments - bỏ qua
                    pass
            else:
                # Chưa giao - kiểm tra deadline đã qua chưa
                if now_vn > deadline:
                    # Chưa giao, trễ ⚠️
                    delivery_stats['not_shipped_late']['sodonhang'] += 1
                    delivery_stats['not_shipped_late']['doanhso'] += amount
        except (ValueError, AttributeError, KeyError) as e:
            # Bỏ qua đơn có lỗi khi parse dữ liệu
            logger.debug(f"[Dashboard] Error processing order for delivery stats: {e}")
            continue
    
    # Tính tổng và phần trăm cho delivery_stats
    total_delivery_orders = (
        delivery_stats['not_shipped_late']['sodonhang'] +
        delivery_stats['shipped_late']['sodonhang'] +
        delivery_stats['shipped_on_time']['sodonhang']
    )
    
    if total_delivery_orders > 0:
        for key in delivery_stats:
            delivery_stats[key]['percent'] = round(
                (delivery_stats[key]['sodonhang'] / total_delivery_orders) * 100, 2
            )
    else:
        for key in delivery_stats:
            delivery_stats[key]['percent'] = 0.0
    
    # Tính toán đơn lỗi/sai sót từ Ticket model
    error_stats = {
        'total_orders': 0,  # Tổng số đơn hàng có lỗi
        'total_damage': 0,  # Tổng thiệt hại (số đơn)
        'by_reason': {},  # Phân loại theo lý do
    }
    
    try:
        from cskh.models import Ticket
        from django.db.models import Q
        from django.utils import timezone as django_timezone
        
        # Lọc ticket có depart='warehouse' (Lỗi của kho hàng) và created_at trong khoảng thời gian lọc
        # Chuyển start_date và end_date sang timezone-aware nếu cần
        start_django = django_timezone.make_aware(start_date) if start_date.tzinfo is None else start_date
        end_django = django_timezone.make_aware(end_date) if end_date.tzinfo is None else end_date
        
        warehouse_tickets = Ticket.objects.filter(
            depart='warehouse',  # Lọc theo bộ phận xử lý là Kho
            created_at__gte=start_django,
            created_at__lte=end_django
        )
        
        # Lọc theo location_id nếu có
        if location_id:
            warehouse_tickets = warehouse_tickets.filter(location_id=location_id)
        
        error_stats['total_orders'] = warehouse_tickets.count()
        error_stats['total_damage'] = warehouse_tickets.count()  # Số đơn hàng = số thiệt hại
        
        # Phân loại theo lý do (lấy từ reason_type hoặc title)
        for ticket in warehouse_tickets:
            # Lấy lý do từ reason_type hoặc title
            reason = ticket.reason_type or ticket.title or 'Khác'
            if reason not in error_stats['by_reason']:
                error_stats['by_reason'][reason] = 0
            error_stats['by_reason'][reason] += 1
            
    except Exception as e:
        logger.warning(f"[Dashboard] Error getting error stats: {e}", exc_info=True)
        error_stats = {
            'total_orders': 0,
            'total_damage': 0,
            'by_reason': {},
        }
    
    return {
        'sum_data': sum_data,
        'doanhso_shipment': doanhso_shipment,  # Doanh số từ shipment note
        'ty_le_sp_don': ty_le_sp_don,  # Tỷ lệ sản phẩm/đơn
        'hieu_suat': {
            'doanhso_h': round(hieu_suat_doanhso_h, 0),  # Doanh số/giờ (làm tròn)
            'don_h': round(hieu_suat_don_h, 1),  # Đơn/giờ (giữ để hiển thị)
            'tong_gio': tong_gio_lam,
            'so_nguoi_goi': so_nguoi_goi,
        },
        'ticket_stats': {
            'total': total_tickets,
            'unprocessed': unprocessed_tickets,
        },
        'deadline_stats': deadline_stats,  # Thống kê deadline: Giao trước 12H, 24H, Trưa mai
        'don_chua_goi': don_chua_goi,  # Đơn chưa gói với phần trăm
        'don_da_goi': don_da_goi,  # Đơn đã gói với phần trăm
        'pending_deadlines': pending_deadlines,
        'pending_sum': pending_sum,
        'per_user': sorted_users,
        'per_category': sorted_categories,
        'carrier_summary': carrier_summary,
        'hourly_data': hourly_data,
        'hourly_categories': hourly_categories,
        'category_chart_data': category_chart_data,  # Dữ liệu biểu đồ categories
        'delivery_stats': delivery_stats,  # Thống kê giao đúng hạn
        'error_stats': error_stats,  # Thống kê đơn lỗi/sai sót
        'top1_doanhso_user': top1_doanhso_user,  # User có TOP 1 doanh số
        'top1_hieu_suat_user': top1_hieu_suat_user,  # User có TOP 1 hiệu suất
        'scope': scope,
        'kho_norm': kho_norm,
    }

