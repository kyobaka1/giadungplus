# kho/views/overview.py
"""
Overview views - Dashboard tổng quan kho hàng.
"""

from django.shortcuts import render
from django.http import JsonResponse
from kho.utils import group_required
from kho.models import WarehousePackingSetting
from core.system_settings import get_connection_ids, SAPO_TMDT, load_shopee_shops, load_shopee_shops_detail
from core.sapo_client import get_sapo_client, BaseFilter
from orders.services.sapo_service import SapoMarketplaceService, SapoCoreOrderService
from kho.services.dashboard_service import calculate_dashboard_stats
from core.shopee_client import ShopeeClient

import logging
import threading
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Mapping kho
LOCATION_BY_KHO = {
    "geleximco": 241737,  # HN
    "toky": 548744,       # HCM
}


def _get_date_range(time_filter: str) -> tuple[datetime, datetime]:
    """
    Lấy date range dựa trên time filter.
    
    Args:
        time_filter: "today", "yesterday", "7days", "30days"
        
    Returns:
        (start_date, end_date) trong timezone VN
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)
    
    if time_filter == "today":
        start_date = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_vn.replace(hour=23, minute=59, second=59, microsecond=0)
    elif time_filter == "yesterday":
        yesterday = now_vn - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
    elif time_filter == "7days":
        start_date = (now_vn - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_vn.replace(hour=23, minute=59, second=59, microsecond=0)
    elif time_filter == "30days":
        start_date = (now_vn - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_vn.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        # Default: today
        start_date = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now_vn.replace(hour=23, minute=59, second=59, microsecond=0)
    
    return start_date, end_date


def _fetch_orders_page(
    core_service: SapoCoreOrderService,
    page: int,
    created_on_min: str,
    created_on_max: str,
    location_id: int,
    lock: threading.Lock,
    all_orders: List[Dict[str, Any]]
) -> int:
    """
    Fetch một page orders trong thread riêng.
    
    Returns:
        Số orders đã fetch
    """
    try:
        params = {
            "created_on_min": created_on_min,
            "created_on_max": created_on_max,
            "status": "draft,finalized,completed",
            "limit": 250,
            "page": page,
            "location_id": location_id,
        }
        
        result = core_service.list_orders(BaseFilter(params=params))
        orders = result.get("orders", [])
        
        if not orders:
            return 0
        
        with lock:
            all_orders.extend(orders)
        
        return len(orders)
    except Exception as e:
        logger.error(f"[Dashboard] Error fetching page {page}: {e}", exc_info=True)
        return 0


def _fetch_orders_multi_thread(
    core_service: SapoCoreOrderService,
    start_date: datetime,
    end_date: datetime,
    location_id: int,
    max_workers: int = 5
) -> List[Dict[str, Any]]:
    """
    Fetch orders với multi-threading để tăng tốc.
    
    Args:
        core_service: SapoCoreOrderService instance
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        location_id: Location ID của kho
        max_workers: Số thread tối đa
        
    Returns:
        List tất cả orders
    """
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    
    # Mở rộng window để lấy đủ orders (có thể có time_packing trong khoảng nhưng created_on ngoài khoảng)
    # Khi time=today: lấy orders từ 2 ngày trước đến hôm nay (vì có thể có đơn tạo 2 ngày trước nhưng gói hôm nay)
    window_start = start_date - timedelta(days=2)
    window_end = end_date + timedelta(days=1)
    
    logger.info(f"[Dashboard] Fetch orders window: {window_start.strftime('%Y-%m-%d %H:%M:%S')} to {window_end.strftime('%Y-%m-%d %H:%M:%S')} (filter range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})")
    
    created_on_min = window_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    created_on_max = window_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    all_orders = []
    lock = threading.Lock()
    
    # Fetch page đầu tiên để biết tổng số
    try:
        params = {
            "created_on_min": created_on_min,
            "created_on_max": created_on_max,
            "status": "draft,finalized,completed",
            "limit": 250,
            "page": 1,
            "location_id": location_id,
        }
        result = core_service.list_orders(BaseFilter(params=params))
        first_page_orders = result.get("orders", [])
        metadata = result.get("metadata", {})
        total = metadata.get("total", 0)
        
        if first_page_orders:
            all_orders.extend(first_page_orders)
        
        # Tính số page cần fetch (giới hạn 50 pages để tránh quá tải)
        if total > 0:
            total_pages = min((total + 249) // 250, 50)  # Ceiling division, max 50 pages
            logger.info(f"[Dashboard] Total orders: {total}, pages: {total_pages}")
            
            # Fetch các page còn lại với multi-threading
            if total_pages > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for page in range(2, total_pages + 1):
                        future = executor.submit(
                            _fetch_orders_page,
                            core_service,
                            page,
                            created_on_min,
                            created_on_max,
                            location_id,
                            lock,
                            all_orders
                        )
                        futures.append(future)
                    
                    # Đợi tất cả hoàn thành
                    for future in as_completed(futures):
                        try:
                            count = future.result()
                            if count == 0:
                                # Không còn orders, cancel các futures còn lại
                                for f in futures:
                                    f.cancel()
                                break
                        except Exception as e:
                            logger.error(f"[Dashboard] Error in thread: {e}", exc_info=True)
        else:
            logger.info(f"[Dashboard] No orders found")
    
    except Exception as e:
        logger.error(f"[Dashboard] Error fetching orders: {e}", exc_info=True)
    
    logger.info(f"[Dashboard] Fetched {len(all_orders)} orders total")
    return all_orders


def _load_category_map() -> Dict[int, str]:
    """
    Load category mapping từ products (từ database cache).
    
    Returns:
        Dict mapping product_id -> category_name
    """
    category_map = {}
    try:
        # Lấy từ database cache thay vì API
        from products.services.product_cache_service import ProductCacheService
        cache_service = ProductCacheService()
        products_data = cache_service.list_products_raw()
        
        for product in products_data:
            product_id = product.get("id")
            category = product.get("category")
            if product_id and category:
                category_map[product_id] = category
    except Exception as e:
        logger.error(f"[Dashboard] Error loading category map: {e}", exc_info=True)
    
    return category_map


@group_required("WarehouseManager")
def dashboard(request):
    """
    Màn hình tổng quan kho:
    - Đơn theo trạng thái (chuẩn bị, đang gói, đã gói...)
    - Thống kê theo người gói
    - Biểu đồ theo giờ
    - Thống kê theo danh mục
    
    Mặc định load theo kho được cài đặt trong request.session.
    """
    # Lấy kho từ session (mặc định là geleximco)
    current_kho = request.session.get("current_kho", "geleximco")
    location_id = LOCATION_BY_KHO.get(current_kho, 241737)
    
    # Nếu có tham số ?kho= trong URL, cập nhật session
    if 'kho' in request.GET:
        kho = request.GET.get("kho")
        if kho in ["geleximco", "toky"]:
            request.session["current_kho"] = kho
            current_kho = kho
            location_id = LOCATION_BY_KHO.get(current_kho, 241737)
    
    # Lấy time filter hoặc datetime từ form
    time_filter = request.GET.get("time", "today")
    time_str = request.GET.get("time")
    end_time_str = request.GET.get("end_time")
    
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    
    # Nếu có datetime từ form và không phải là filter preset, ưu tiên dùng datetime
    if time_str and end_time_str and time_str not in ["today", "yesterday", "7days", "30days"]:
        try:
            # Parse datetime từ form (format: YYYY-MM-DDTHH:mm hoặc YYYY-MM-DD)
            if "T" in time_str:
                start_date = datetime.strptime(time_str, "%Y-%m-%dT%H:%M").replace(tzinfo=tz_vn)
            else:
                start_date = datetime.strptime(time_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz_vn)
            
            if "T" in end_time_str:
                end_date = datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M").replace(tzinfo=tz_vn)
            else:
                end_date = datetime.strptime(end_time_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=tz_vn)
        except (ValueError, TypeError) as e:
            logger.warning(f"[Dashboard] Error parsing datetime: {e}, fallback to time_filter")
            # Nếu parse lỗi, fallback về time_filter
            start_date, end_date = _get_date_range(time_filter)
    else:
        # Dùng time_filter
        start_date, end_date = _get_date_range(time_filter)
    
    # Service layer
    core_service = SapoCoreOrderService()
    
    # Fetch orders với multi-threading
    start_fetch = time.time()
    orders = _fetch_orders_multi_thread(
        core_service,
        start_date,
        end_date,
        location_id,
        max_workers=5
    )
    fetch_time = time.time() - start_fetch
    logger.info(f"[Dashboard] Fetched {len(orders)} orders in {fetch_time:.2f}s")
    
    # Load category map
    category_map = _load_category_map()
    
    # Tính toán thống kê
    start_calc = time.time()
    stats = calculate_dashboard_stats(
        orders,
        location_id,
        start_date,
        end_date,
        category_map
    )
    calc_time = time.time() - start_calc
    logger.info(f"[Dashboard] Calculated stats in {calc_time:.2f}s")
    
    # Lấy cài đặt packing cho cả 2 kho
    packing_settings = {}
    for warehouse_code in ['KHO_HCM', 'KHO_HN']:
        setting = WarehousePackingSetting.get_setting_for_warehouse(warehouse_code)
        packing_settings[warehouse_code] = {
            'is_active': setting.is_active,
            'warehouse_display': setting.get_warehouse_code_display(),
        }
    
    # Serialize hourly data for JavaScript
    hourly_data_json = json.dumps(stats.get('hourly_data', [])) if stats else '[]'
    hourly_categories_json = json.dumps(stats.get('hourly_categories', [])) if stats else '[]'
    
    # Serialize category chart data for JavaScript
    category_chart_data = stats.get('category_chart_data', {}) if stats else {}
    category_chart_data_json = json.dumps(category_chart_data) if category_chart_data else '{}'
    
    # Update stats with serialized data for template
    if stats:
        stats['category_chart_data'] = category_chart_data_json
    
    # Lấy dữ liệu tồn kho (inventory)
    inventory_data = None
    try:
        sapo = get_sapo_client()
        # Lấy tồn kho cho cả 2 kho
        def fetch_onhand(location_id):
            try:
                url = f"https://sisapsan.mysapogo.com/admin/reports/inventories/onhand.json?page=1&limit=1&location_ids={location_id}"
                response = sapo.core_session.get(url)
                if response.status_code == 200:
                    return response.json().get("summary", {})
                return {}
            except Exception as e:
                logger.error(f"[Dashboard] Error fetching inventory for location {location_id}: {e}")
                return {}
        
        gele_inv = fetch_onhand(241737)  # Hà Nội
        toky_inv = fetch_onhand(548744)  # Sài Gòn
        
        gele_onhand = int(gele_inv.get("total_local_onhand", 0))
        gele_amount = int(gele_inv.get("total_local_amount", 0))
        toky_onhand = int(toky_inv.get("total_local_onhand", 0))
        toky_amount = int(toky_inv.get("total_local_amount", 0))
        
        sum_onhand = gele_onhand + toky_onhand
        sum_amount = (gele_amount or 0) + (toky_amount or 0)
        
        inventory_data = {
            "gele": {"onhand": gele_onhand, "amount": gele_amount},
            "toky": {"onhand": toky_onhand, "amount": toky_amount},
            "sum": {"onhand": sum_onhand, "amount": sum_amount},
        }
        logger.info(f"[Dashboard] Loaded inventory data: sum={sum_onhand} items, {sum_amount} VND")
    except Exception as e:
        logger.error(f"[Dashboard] Error loading inventory data: {e}", exc_info=True)
        inventory_data = None
    
    # Lấy dữ liệu hiệu quả shop Shopee
    shop_performance = {}
    try:
        # Lấy tất cả shops từ config (bao gồm detail để có field mall)
        shops_detail = load_shopee_shops_detail()
        shops_map = load_shopee_shops()
        
        # Lấy tất cả shop names từ config
        all_shops = list(shops_map.keys())
        
        for shop_name in all_shops:
            # Lấy thông tin chi tiết shop (để có field mall)
            shop_info = shops_detail.get(shop_name, {})
            is_mall = shop_info.get("mall", 0) == 1
                
            try:
                # Khởi tạo ShopeeClient với shop
                client = ShopeeClient(shop_key=shop_name)
                
                # API 1: Lấy shop performance metrics
                url_1 = "https://banhang.shopee.vn/api/sellergrowth/v2/ps/landing_page/"
                params_1 = {
                    "SPC_CDS": "fa75a215-26fc-4960-8efc-1b1d87508841",
                    "SPC_CDS_VER": "2"
                }
                response_1 = client.session.get(url_1, params=params_1, timeout=10)
                if response_1.status_code == 200:
                    data_1 = response_1.json()
                    metrics = data_1.get("metrics", [])  # metrics là array
                else:
                    metrics = []
                
                # API 2: Lấy ongoing points
                url_2 = "https://banhang.shopee.vn/api/v2/shops/sellerCenter/ongoingPoints/"
                params_2 = {
                    "SPC_CDS": "fa75a215-26fc-4960-8efc-1b1d87508841",
                    "SPC_CDS_VER": "2"
                }
                response_2 = client.session.get(url_2, params=params_2, timeout=10)
                if response_2.status_code == 200:
                    data_2 = response_2.json()
                    ongoing_points = data_2.get("data", {})
                else:
                    ongoing_points = {}
                
                # Format tên shop để hiển thị (replace _ bằng space và title case)
                shop_display_name = shop_name.replace("_", " ").title()
                
                # Tìm 3 metrics cần thiết: sd, nfr, lsr
                metrics_dict = {}
                for metric in metrics:
                    metric_key = metric.get("metric_key")
                    if metric_key in ["sd", "nfr", "lsr"]:
                        metrics_dict[metric_key] = {
                            "value": metric.get("metric_value"),
                            "status": metric.get("status")  # 1 = bad (warning), 0 = good
                        }
                
                shop_performance[shop_name] = {
                    "shop_name": shop_display_name,
                    "shop_performance": metrics_dict,
                    "total_points": ongoing_points.get("totalPoints", 0),
                    "is_mall": is_mall
                }
                
                logger.info(f"[Dashboard] Loaded shop performance for {shop_name}")
            except Exception as e:
                logger.error(f"[Dashboard] Error loading shop performance for {shop_name}: {e}", exc_info=True)
                shop_performance[shop_name] = None
        
        if not shop_performance:
            shop_performance = None
            
    except Exception as e:
        logger.error(f"[Dashboard] Error loading shop performance: {e}", exc_info=True)
        shop_performance = None
    
    # Context
    context = {
        "title": "Kho – Overview",
        "current_kho": current_kho,
        "location_id": location_id,
        "time_filter": time_filter,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "stats": stats,
        "packing_settings": packing_settings,
        "fetch_time": round(fetch_time, 2),
        "calc_time": round(calc_time, 2),
        "hourly_data_json": hourly_data_json,
        "hourly_categories_json": hourly_categories_json,
        "inventory_data": inventory_data,
        "shop_performance": shop_performance,
    }
    
    return render(request, "kho/overview.html", context)
