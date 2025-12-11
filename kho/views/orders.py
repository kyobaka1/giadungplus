# kho/views/orders.py
from typing import Any, Dict, List

from core.system_settings import get_connection_ids
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from kho.utils import group_required
from core.sapo_client import BaseFilter
from orders.services.sapo_service import (
    SapoMarketplaceService,
    SapoCoreOrderService,
)
from orders.services.dto import OrderDTO
from orders.services.order_builder import build_order_from_sapo
import os
from io import BytesIO
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from PyPDF2 import PdfReader, PdfWriter  # pip install PyPDF2
from orders.services.sapo_service import SapoMarketplaceService
from orders.services.dto import MarketplaceConfirmOrderDTO
from core.system_settings import is_geleximco_address
from orders.services.shopee_print_service import (
    generate_label_pdf_for_channel_order, 
    extract_customer_info,
    set_debug_mode,
)
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET
import json
import logging
import base64

logger = logging.getLogger(__name__)

connection_ids = get_connection_ids()
LOCATION_BY_KHO = {
    "geleximco": 241737,  # HN
    "toky": 548744,       # HCM
}
BILL_DIR = "settings/logs/bill"

# Tắt debug print mặc định để tránh log nhiều trong module kho
DEBUG_PRINT_ENABLED = False

def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)

@group_required("WarehouseManager")
def prepare_and_print(request):
    """
    Màn hình:
    - Nhập mã đơn / scan
    - Hiển thị danh sách đơn cần chuẩn bị
    - Nút in đơn (gửi xuống client / in PDF)
    """
    # TODO: gọi service lấy danh sách đơn trạng thái 'chờ xử lý'
    context = {
        "title": "Chuẩn bị & In đơn",
        "orders": [],
    }
    return render(request, "kho/orders/prepare_print.html", context)

@group_required("WarehouseManager")
def express_orders(request):
    """
    Đơn hoả tốc:
    - Lấy danh sách đơn từ Marketplace API (Sapo Marketplace)
    - Lọc theo kho đang chọn trong session (geleximco / toky)
    - Gắn thêm thông tin Sapo core order (location_id, shipment, customer...)
    """

    context = {
        "title": "HOẢ TỐC SHOPEE - GIA DỤNG PLUS",
        "orders": [],
    }

    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    # Service layer
    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()

    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)

    # Filter cho Marketplace orders
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 50, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED","shippingCarrierIds":"134097,1285481,108346,17426,60176,1283785,1285470,1292451,35696,47741,14895,1272209,176002,4329", "sortBy": "ISSUED_AT", "orderBy": "desc", })

    mp_resp = mp_service.list_orders(mp_filter)
    mp_orders = mp_resp.get("orders", [])
    debug_print(f"express_orders filter: {mp_filter.params}")
    debug_print(f"express_orders fetched {len(mp_orders)} orders from MP")

    filtered_orders = []

    for o in mp_orders:
        if o["sapo_order_id"]:
            # 1) Thời gian tạo đơn (issued_at là timestamp – giây)
            ts = o.get("issued_at", 0) or 0
            dt = datetime.fromtimestamp(ts, tz_vn)
            o["issued_dt"] = dt
            diff = now_vn - dt
            seconds = diff.total_seconds()
            if seconds < 60:
                o["issued_ago"] = f"{int(seconds)} giây trước"
            elif seconds < 3600:
                o["issued_ago"] = f"{int(seconds // 60)} phút trước"
            elif seconds < 86400:
                o["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
            else:
                days = int(seconds // 86400)
                o["issued_ago"] = f"{days} ngày trước"

        # 2) Kiểm tra nếu là đơn vị "Nhanh" (shippingCarrierIds=59778) -> sync đơn trước
        mp_order_id = o.get("id")
        shipping_carrier_id = o.get("shipping_carrier_id") or o.get("shippingCarrierId")
        shipping_carrier_name = o.get("shipping_carrier_name", "") or ""
        
        is_nhanh_carrier = (
            shipping_carrier_id == 59778 
            or "nhanh" in shipping_carrier_name.lower()
        )
        
        if is_nhanh_carrier and mp_order_id:
            try:
                # Gửi PUT request sync đơn
                from core.sapo_client import get_sapo_client
                sapo = get_sapo_client()
                sync_url = f"https://market-place.sapoapps.vn/v2/orders/sync?ids={mp_order_id}&accountId=319911"
                sapo.tmdt_session.put(sync_url)
                # Đợi 0.5 giây
                time.sleep(0.5)
            except Exception as sync_err:
                # Không block nếu sync lỗi, chỉ log
                pass
        
        # 3) Lấy Sapo core order (DTO) theo sapo_order_id
        sapo_order_id = o.get("sapo_order_id")
        if not sapo_order_id:
            # Không map được về đơn core → bỏ qua
            debug_print(f"express_orders Skip order {o.get('id')} - No sapo_order_id")
            continue

        try:
            order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
        except Exception as e:
            # Nếu lỗi gọi API / parse thì bỏ qua đơn này
            debug_print(f"express_orders Skip order {o.get('id')} - Error getting DTO: {e}")
            continue

        # 3) Lọc theo kho (location_id)
        # Location filter disabled to show all orders
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            debug_print(f"express_orders Skip order {o.get('id')} - Location mismatch: {order_dto.location_id} != {allowed_location_id}")
            continue

        # 4) Gắn thêm info từ DTO cho template dùng
        o["sapo_location_id"] = order_dto.location_id
        o["sapo_order_code"] = order_dto.code
        o["sapo_channel"] = order_dto.channel
        o["sapo_reference_number"] = order_dto.reference_number
        o["shop_name"] = order_dto.shop_name
        # Thông tin khách hàng / địa chỉ
        o["customer_name"] = order_dto.customer_name
        o["customer_phone"] = order_dto.customer_phone
        o["shipping_address_line"] = order_dto.shipping_address_line
        # Lấy thông tin vận chuyển từ fulfillments cuối cùng (nếu có)
        shipment_name = None
        tracking_code = None

        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                shipment_name = last_f.shipment.service_name
                tracking_code = last_f.shipment.tracking_code

        # Ưu tiên dữ liệu core, fallback về dữ liệu Marketplace
        o["shipping_carrier_name"] = (
            shipment_name or o.get("shipping_carrier_name")
        )
        o["tracking_code"] = tracking_code or o.get("tracking_code")
        # Thêm packing_status để template có thể hiển thị hiệu ứng gạch đỏ chéo
        o["packing_status"] = order_dto.packing_status or 0
        # Option: đính luôn DTO để template muốn đào sâu thì xài
        o["sapo_order_dto"] = order_dto
        filtered_orders.append(o)

    context["orders"] = filtered_orders
    context["current_kho"] = current_kho
    return render(request, "kho/orders/order_express.html", context)


@group_required("WarehouseManager")
def shopee_orders(request):
    """
    Đơn Shopee, Tiktok:
    - Lấy danh sách đơn từ Marketplace API (Sapo Marketplace)
    - Lọc theo kho đang chọn trong session (geleximco / toky)
    - Gắn thêm thông tin Sapo core order (location_id, shipment, customer...)
    """
    # ========== DEBUG: Track thời gian ==========
    start_time = time.time()
    api_call_count = {"marketplace": 0, "get_order": 0, "get_variant": 0}

    context = {
        "title": "ĐƠN SHOPEE - GIA DỤNG PLUS",
        "orders": [],
    }

    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    # Service layer
    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()

    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)

    # Filter cho Marketplace orders
    step_start = time.time()
    all_orders = []
    page = 1
    limit = 250
    
    debug_print(f"shopee_orders Starting to fetch marketplace orders (limit {limit} per page)...")
    logger.info(f"[PERF] shopee_orders: Starting to fetch marketplace orders...")
    
    while True:
        mp_filter = BaseFilter(params={ 
            "connectionIds": connection_ids, 
            "page": page, 
            "limit": limit, 
            "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", 
            "shippingCarrierIds": "51237,1218211,68301,36287,1218210,4110,59778,3411,1236070,37407,171067,1270129,57740,1236040,55646,166180,1289173,4095",
            "sortBy": "ISSUED_AT", 
            "orderBy": "desc", 
        })
        
        page_start = time.time()
        mp_resp = mp_service.list_orders(mp_filter)
        api_call_count["marketplace"] += 1
        page_time = time.time() - page_start
        logger.info(f"[PERF] shopee_orders: Page {page} marketplace API call took {page_time:.2f}s")
        
        orders = mp_resp.get("orders", [])
        metadata = mp_resp.get("metadata", {})
        total = metadata.get("total", 0)
        
        all_orders.extend(orders)
        debug_print(f"shopee_orders fetched page {page}: {len(orders)} orders in {page_time:.2f}s. Total so far: {len(all_orders)}/{total}")
        
        if not orders or len(all_orders) >= total:
            break
            
        page += 1
        
    fetch_time = time.time() - step_start
    mp_orders = all_orders
    debug_print(f"shopee_orders finished fetching. Total: {len(mp_orders)} orders in {fetch_time:.2f}s")
    logger.info(f"[PERF] shopee_orders: Fetched {len(mp_orders)} marketplace orders in {fetch_time:.2f}s ({api_call_count['marketplace']} API calls)")

    # ========== OPTIMIZATION: Fetch list orders trước để cache ==========
    step_start = time.time()
    debug_print(f"shopee_orders Pre-fetching recent orders from Sapo Core API to cache...")
    logger.info(f"[PERF] shopee_orders: Pre-fetching recent orders to cache...")
    
    # Collect tất cả sapo_order_ids cần fetch
    sapo_order_ids = set()
    for o in mp_orders:
        sapo_order_id = o.get("sapo_order_id")
        if sapo_order_id:
            sapo_order_ids.add(sapo_order_id)
    
    debug_print(f"shopee_orders Need to fetch {len(sapo_order_ids)} unique orders")
    
    # Fetch list orders từ Sapo Core API (1500 orders gần nhất = 6 pages)
    orders_cache: Dict[int, Dict[str, Any]] = {}  # {order_id: raw_order_data}
    cache_fetch_start = time.time()
    page = 1
    limit = 250
    max_pages = 6  # 6 pages = 1500 orders
    
    cache_api_calls = 0
    while page <= max_pages:
        try:
            filters = {
                "status": "draft,finalized",  # Lấy cả draft và finalized
                "limit": limit,
                "page": page,
            }
            
            # Thêm location_id filter nếu có
            if allowed_location_id:
                filters["location_id"] = allowed_location_id
            
            page_start = time.time()
            raw_response = core_service._core_api.list_orders_raw(**filters)
            cache_api_calls += 1
            page_time = time.time() - page_start
            logger.info(f"[PERF] shopee_orders: Cache fetch page {page} took {page_time:.2f}s")
            
            orders_data = raw_response.get("orders", [])
            
            if not orders_data:
                break
            
            # Cache orders vào dict
            for order_data in orders_data:
                order_id = order_data.get("id")
                if order_id and order_id in sapo_order_ids:
                    orders_cache[order_id] = order_data
            
            debug_print(f"shopee_orders Cache page {page}: {len(orders_data)} orders, matched {len([o for o in orders_data if o.get('id') in sapo_order_ids])} needed orders")
            
            # Check nếu đã cache đủ orders cần thiết
            if len(orders_cache) >= len(sapo_order_ids):
                debug_print(f"shopee_orders Cache complete: {len(orders_cache)}/{len(sapo_order_ids)} orders found")
                break
            
            # Check nếu hết orders
            if len(orders_data) < limit:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"shopee_orders Error fetching cache page {page}: {e}", exc_info=True)
            break
    
    cache_fetch_time = time.time() - cache_fetch_start
    debug_print(f"shopee_orders Cache fetch completed: {len(orders_cache)}/{len(sapo_order_ids)} orders in {cache_fetch_time:.2f}s ({cache_api_calls} API calls)")
    logger.info(f"[PERF] shopee_orders: Cache fetch completed: {len(orders_cache)}/{len(sapo_order_ids)} orders in {cache_fetch_time:.2f}s")
    
    # Convert orders sang DTO và filter
    convert_start = time.time()
    filtered_orders = []
    convert_errors = 0
    skipped_no_sapo_id = 0
    skipped_location = 0
    skipped_packed = 0
    cache_hits = 0
    cache_misses = 0
    
    debug_print(f"shopee_orders Starting to convert {len(mp_orders)} orders to DTO...")
    logger.info(f"[PERF] shopee_orders: Starting to convert {len(mp_orders)} orders to DTO...")

    for o in mp_orders:
        if o["sapo_order_id"]:
            # 1) Thời gian tạo đơn (issued_at là timestamp – giây)
            ts = o.get("created_at", 0) or 0
            dt = datetime.fromtimestamp(ts, tz_vn)
            o["issued_dt"] = dt
            diff = now_vn - dt
            seconds = diff.total_seconds()
            if seconds < 60:
                o["issued_ago"] = f"{int(seconds)} giây trước"
            elif seconds < 3600:
                o["issued_ago"] = f"{int(seconds // 60)} phút trước"
            elif seconds < 86400:
                o["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
            else:
                days = int(seconds // 86400)
                o["issued_ago"] = f"{days} ngày trước"

        # 2) Kiểm tra nếu là đơn vị "Nhanh" (shippingCarrierIds=59778) -> sync đơn trước
        mp_order_id = o.get("id")
        shipping_carrier_id = o.get("shipping_carrier_id") or o.get("shippingCarrierId")
        shipping_carrier_name = o.get("shipping_carrier_name", "") or ""
        
        is_nhanh_carrier = (
            shipping_carrier_id == 59778 
            or "nhanh" in shipping_carrier_name.lower()
        )
        
        if is_nhanh_carrier and mp_order_id:
            try:
                # Gửi PUT request sync đơn
                from core.sapo_client import get_sapo_client
                sapo = get_sapo_client()
                sync_url = f"https://market-place.sapoapps.vn/v2/orders/sync?ids={mp_order_id}&accountId=319911"
                sapo.tmdt_session.put(sync_url)
                # Đợi 0.5 giây
                time.sleep(0.5)
            except Exception as sync_err:
                # Không block nếu sync lỗi, chỉ log
                pass
        
        # 3) Lấy Sapo core order (DTO) theo sapo_order_id
        sapo_order_id = o.get("sapo_order_id")
        if not sapo_order_id:
            # Không map được về đơn core → bỏ qua
            skipped_no_sapo_id += 1
            debug_print(f"shopee_orders Skip order {o.get('id')} - No sapo_order_id")
            continue

        try:
            import threading
            # Setup thread-local counter để track variant API calls
            if not hasattr(threading.current_thread(), 'variant_api_counter'):
                threading.current_thread().variant_api_counter = 0
            
            dto_start = time.time()
            variant_api_calls_before = threading.current_thread().variant_api_counter
            
            # Check cache trước
            if sapo_order_id in orders_cache:
                # Dùng data từ cache
                cache_hits += 1
                cached_data = orders_cache[sapo_order_id]
                debug_print(f"shopee_orders Using cached data for order {sapo_order_id}")
                order_dto: OrderDTO = build_order_from_sapo(cached_data, sapo_client=core_service._sapo)
            else:
                # Không có trong cache, gọi API riêng lẻ
                cache_misses += 1
                debug_print(f"shopee_orders Cache miss, calling API: GET /orders/{sapo_order_id}.json")
                order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
                api_call_count["get_order"] += 1
            
            dto_time = time.time() - dto_start
            variant_api_calls_during = threading.current_thread().variant_api_counter - variant_api_calls_before
            api_call_count["get_variant"] += variant_api_calls_during
            
            # Log chi tiết cho mỗi order
            if variant_api_calls_during > 0:
                debug_print(f"shopee_orders Order {sapo_order_id} DTO conversion took {dto_time:.2f}s (variant API calls: {variant_api_calls_during})")
            else:
                debug_print(f"shopee_orders Order {sapo_order_id} DTO conversion took {dto_time:.2f}s (no additional API calls)")
        except Exception as e:
            # Nếu lỗi gọi API / parse thì bỏ qua đơn này
            convert_errors += 1
            debug_print(f"shopee_orders Skip order {o.get('id')} - Error getting DTO: {e}")
            continue

        # 3) Lọc theo kho (location_id)
        # Location filter disabled to show all orders
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            skipped_location += 1
            continue

        # 3) Lọc theo packing_status (chỉ lấy đơn chưa xử lý, bỏ qua đã in/đã gói)
        if order_dto.packing_status and order_dto.packing_status >= 3:
            skipped_packed += 1
            debug_print(f"shopee_orders Skip order {o.get('id')} - Already processed (status={order_dto.packing_status})")
            continue

        # 4) Gắn thêm info từ DTO cho template dùng
        o["sapo_location_id"] = order_dto.location_id
        o["sapo_order_code"] = order_dto.code
        o["sapo_channel"] = order_dto.channel
        o["sapo_reference_number"] = order_dto.reference_number
        o["shop_name"] = order_dto.shop_name
        # Thông tin khách hàng / địa chỉ
        o["customer_name"] = order_dto.customer_name
        o["customer_phone"] = order_dto.customer_phone
        o["shipping_address_line"] = order_dto.shipping_address_line

        o["deadline"] = order_dto.ship_deadline_fast_str

        # Lấy thông tin vận chuyển từ fulfillments cuối cùng (nếu có)
        shipment_name = None
        tracking_code = None

        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                shipment_name = last_f.shipment.service_name
                tracking_code = last_f.shipment.tracking_code

        # Ưu tiên dữ liệu core, fallback về dữ liệu Marketplace
        o["shipping_carrier_name"] = (
            shipment_name or o.get("shipping_carrier_name")
        )
        o["tracking_code"] = tracking_code or o.get("tracking_code")
        # Option: đính luôn DTO để template muốn đào sâu thì xài
        o["sapo_order_dto"] = order_dto
        
        # 5) Update product_name và variant_name từ DTO nếu products đã tồn tại trong o
        if "products" in o and o["products"]:
            for mp_product in o["products"]:
                # Lấy ID từ Marketplace product để match
                mp_id = mp_product.get("sapo_variant_id")
                
                if mp_id:
                    # Duyệt trong order_dto.line_items để tìm match
                    for dto_item in order_dto.line_items:
                        # Match theo id hoặc variant_id
                        if dto_item.id == mp_id or dto_item.variant_id == mp_id:
                            mp_product["product_name"] = dto_item.product_name or ""
                            mp_product["variant_name"] = dto_item.variant_name or ""
                            break
        
        filtered_orders.append(o)

    convert_time = time.time() - convert_start
    debug_print(f"shopee_orders Converted {len(filtered_orders)} orders in {convert_time:.2f}s "
                f"(errors: {convert_errors}, cache_hits: {cache_hits}, cache_misses: {cache_misses}, "
                f"skipped: no_sapo_id={skipped_no_sapo_id}, location={skipped_location}, packed={skipped_packed})")
    logger.info(f"[PERF] shopee_orders: Converted {len(filtered_orders)} orders in {convert_time:.2f}s "
                f"(errors: {convert_errors}, cache_hits: {cache_hits}, cache_misses: {cache_misses}, "
                f"skipped: no_sapo_id={skipped_no_sapo_id}, location={skipped_location}, packed={skipped_packed})")

    # Tổng kết
    total_time = time.time() - start_time
    debug_print(f"shopee_orders TOTAL TIME: {total_time:.2f}s | "
                f"API calls: marketplace={api_call_count['marketplace']}, cache_fetch={cache_api_calls}, get_order={api_call_count['get_order']} | "
                f"Orders: fetched={len(mp_orders)}, converted={len(filtered_orders)}, "
                f"cache_hits={cache_hits}, cache_misses={cache_misses}, "
                f"errors={convert_errors}, skipped={skipped_no_sapo_id + skipped_location + skipped_packed}")
    logger.info(f"[PERF] shopee_orders: TOTAL TIME: {total_time:.2f}s | "
                f"API calls: marketplace={api_call_count['marketplace']}, cache_fetch={cache_api_calls}, get_order={api_call_count['get_order']} | "
                f"Orders: fetched={len(mp_orders)}, converted={len(filtered_orders)}, "
                f"cache_hits={cache_hits}, cache_misses={cache_misses}, "
                f"errors={convert_errors}, skipped={skipped_no_sapo_id + skipped_location + skipped_packed}")

    context["orders"] = filtered_orders[::-1]
    context["current_kho"] = current_kho

    return render(request, "kho/orders/shopee_orders.html", context)


# ==================== NEW VIEWS (skeleton implementations) ====================

@group_required("WarehouseManager")
def sapo_orders(request):
    """
    Đơn Sapo:
    - Lấy danh sách đơn từ Sapo Core API -> Đơn giao ngoài Facebook, Zalo, CSKH (ngoài sàn).
    - Lọc theo kho đang chọn trong session (geleximco / toky)
    - Filter: status=finalized, packed_status=processing,packed, composite_fulfillment_status=wait_to_pack,packed_processing,packed
    """
    from core.sapo_client import get_sapo_client
    from orders.services.order_builder import OrderDTOFactory
    from kho.services.product_service import load_all_products, get_variant_image
    from kho.services.order_source_service import load_all_order_sources
    from kho.services.delivery_provider_service import get_provider_name

    # ========== DEBUG: Track thời gian ==========
    start_time = time.time()
    api_call_count = {"list_orders": 0, "get_variant": 0}
    
    context = {
        "title": "ĐƠN SAPO - GIA DỤNG PLUS",
        "orders": [],
    }

    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    # Service layer
    sapo = get_sapo_client()
    core_repo = sapo.core
    factory = OrderDTOFactory()
    
    # Load products với images để map vào line items
    step_start = time.time()
    debug_print("sapo_orders Loading products with images...")
    logger.info("[PERF] sapo_orders: Starting load_all_products...")
    try:
        load_all_products()
        step_time = time.time() - step_start
        debug_print(f"sapo_orders Products loaded successfully in {step_time:.2f}s")
        logger.info(f"[PERF] sapo_orders: load_all_products completed in {step_time:.2f}s")
    except Exception as e:
        step_time = time.time() - step_start
        logger.warning(f"sapo_orders Error loading products: {e} (took {step_time:.2f}s)", exc_info=True)
        debug_print(f"sapo_orders Error loading products: {e}")
    
    # Load order sources để map source_id -> source_name
    step_start = time.time()
    debug_print("sapo_orders Loading order sources...")
    logger.info("[PERF] sapo_orders: Starting load_all_order_sources...")
    try:
        load_all_order_sources()
        step_time = time.time() - step_start
        debug_print(f"sapo_orders Order sources loaded successfully in {step_time:.2f}s")
        logger.info(f"[PERF] sapo_orders: load_all_order_sources completed in {step_time:.2f}s")
    except Exception as e:
        step_time = time.time() - step_start
        logger.warning(f"sapo_orders Error loading order sources: {e} (took {step_time:.2f}s)", exc_info=True)
        debug_print(f"sapo_orders Error loading order sources: {e}")

    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)

    # Lấy orders từ Sapo Core API với filter
    step_start = time.time()
    all_orders = []
    page = 1
    limit = 250
    max_pages = 15  # Giới hạn 15 trang như user code
    
    logger.info(f"[PERF] sapo_orders: Starting to fetch orders (max {max_pages} pages, {limit} per page)...")
    debug_print(f"sapo_orders Starting to fetch orders (max {max_pages} pages, {limit} per page)...")
    
    while page <= max_pages:
        try:
            # Filter theo yêu cầu: status=finalized, packed_status=processing,packed, composite_fulfillment_status=wait_to_pack,packed_processing,packed
            filters = {
                "status": "finalized",
                "fulfillment_status":"unshipped",
                "packed_status": "processing,packed",
                "composite_fulfillment_status": "wait_to_pack,packed_processing,packed,packed_cancelled_client",
                "limit": limit,
                "page": page,
            }
            
            # Thêm location_id filter nếu có
            if allowed_location_id:
                filters["location_id"] = allowed_location_id
            
            page_start = time.time()
            logger.info(f"[PERF] sapo_orders: Fetching page {page} with filters: {filters}")
            raw_response = core_repo.list_orders_raw(**filters)
            api_call_count["list_orders"] += 1
            page_time = time.time() - page_start
            logger.info(f"[PERF] sapo_orders: Page {page} fetched in {page_time:.2f}s")
            
            orders_data = raw_response.get("orders", [])
            
            if not orders_data:
                logger.info(f"[PERF] sapo_orders: Page {page} returned no orders, stopping pagination")
                break
            
            all_orders.extend(orders_data)
            debug_print(f"sapo_orders fetched page {page}: {len(orders_data)} orders in {page_time:.2f}s. Total so far: {len(all_orders)}")
            
            page += 1
            
        except Exception as e:
            logger.error(f"sapo_orders Error fetching page {page}: {e}", exc_info=True)
            break
    
    fetch_time = time.time() - step_start
    debug_print(f"sapo_orders finished fetching. Total: {len(all_orders)} orders in {fetch_time:.2f}s")
    logger.info(f"[PERF] sapo_orders: Fetched {len(all_orders)} orders in {fetch_time:.2f}s ({api_call_count['list_orders']} API calls)")

    # Convert orders sang DTO
    step_start = time.time()
    filtered_orders = []
    convert_errors = 0
    variant_api_calls_before = api_call_count["get_variant"]
    
    logger.info(f"[PERF] sapo_orders: Starting to convert {len(all_orders)} orders to DTO...")
    debug_print(f"sapo_orders Starting to convert {len(all_orders)} orders to DTO...")

    for idx, raw_order in enumerate(all_orders):
        try:
            # Convert raw order sang DTO
            order_dto: OrderDTO = factory.from_sapo_json(raw_order, sapo_client=sapo)
            # Track variant API calls (nếu có)
            if api_call_count["get_variant"] > variant_api_calls_before:
                variant_api_calls_before = api_call_count["get_variant"]
        except Exception as e:
            convert_errors += 1
            logger.warning(f"sapo_orders Skip order {raw_order.get('id')} - Error parsing DTO: {e}")
            continue

        # Lọc theo kho (location_id) - đã filter ở API level nhưng double check
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue

        # CHỈ lọc đơn ngoài sàn (bỏ qua đơn sàn TMĐT)
        if order_dto.is_marketplace_order:
            debug_print(f"sapo_orders Skip order {order_dto.id} - Đây là đơn sàn TMĐT (is_marketplace_order=True)")
            continue

        # Parse created_on từ ISO string sang datetime
        created_dt = None
        if order_dto.created_on:
            try:
                # Parse ISO string format (có thể có hoặc không có timezone)
                created_dt = datetime.fromisoformat(order_dto.created_on.replace('Z', '+00:00'))
                # Đảm bảo có timezone, nếu không thì gán VN timezone
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=tz_vn)
                # Convert về VN timezone nếu cần
                if created_dt.tzinfo != tz_vn:
                    created_dt = created_dt.astimezone(tz_vn)
            except (ValueError, AttributeError) as e:
                logger.warning(f"sapo_orders Error parsing created_on for order {order_dto.id}: {e}")
                created_dt = None

        # Tạo dict cho template (tương tự shopee_orders nhưng không có shop_name, channel_order_number)
        o = {
            "id": order_dto.id,
            "sapo_order_id": order_dto.id,
            "sapo_order_code": order_dto.code,
            "sapo_location_id": order_dto.location_id,
            "sapo_channel": order_dto.channel or "Sapo",
            "sapo_source_name": order_dto.source_name or "",  # Tên nguồn đơn hàng (từ source_id)
            "sapo_reference_number": order_dto.reference_number or "",
            
            # Thông tin khách hàng
            "customer_name": order_dto.customer_name or "",
            "customer_phone": order_dto.customer_phone or "",
            "shipping_address_line": order_dto.shipping_address_line or "",
            
            # Thời gian
            "created_at": created_dt.timestamp() if created_dt else 0,
            "issued_dt": created_dt or now_vn,
            
            # Deadline
            "deadline": order_dto.ship_deadline_fast_str or "",
            
            # Products - từ line_items
            "products": [],
            
            # Shipping
            "shipping_carrier_name": "",
            "dvvc": "",
            "tracking_code": "",
        }
        
        # Tính thời gian đã trôi qua
        if created_dt:
            diff = now_vn - created_dt
            seconds = diff.total_seconds()
            if seconds < 60:
                o["issued_ago"] = f"{int(seconds)} giây trước"
            elif seconds < 3600:
                o["issued_ago"] = f"{int(seconds // 60)} phút trước"
            elif seconds < 86400:
                o["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
            else:
                days = int(seconds // 86400)
                o["issued_ago"] = f"{days} ngày trước"
        else:
            o["issued_ago"] = ""

        # Lấy thông tin vận chuyển từ fulfillments cuối cùng (nếu có)
        shipment_name = None
        tracking_code = None

        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                # Lấy tracking code
                tracking_code = last_f.shipment.tracking_code
                
                # Lấy delivery_service_provider_id từ shipment
                delivery_provider_id = last_f.shipment.delivery_service_provider_id
                
                # Ưu tiên lấy từ service_name nếu có, nếu không thì lấy từ delivery_provider_id
                shipment_name = last_f.shipment.service_name
                
                # Nếu không có service_name, lấy từ delivery_provider_id
                if not shipment_name and delivery_provider_id:
                    shipment_name = get_provider_name(delivery_provider_id)

        o["shipping_carrier_name"] = shipment_name or ""
        o["dvvc"] = shipment_name or ""
        o["tracking_code"] = tracking_code or ""
        
        # Tạo products list từ line_items
        products = []
        for line_item in order_dto.line_items:
            # Lấy image từ product service (variant_id -> image_url mapping)
            image_url = get_variant_image(line_item.variant_id) if line_item.variant_id else ""
            
            product_dict = {
                "id": line_item.id,
                "product_id": line_item.product_id,
                "variant_id": line_item.variant_id,
                "product_name": line_item.product_name or "",
                "variant_name": line_item.variant_name or "",
                "sku": line_item.sku or "",
                "quantity": int(line_item.quantity) if line_item.quantity else 0,
                "price": float(line_item.price) if line_item.price else 0.0,
                "image": image_url,  # Lấy từ product service (variant_id -> image_url)
            }
            products.append(product_dict)
        
        o["products"] = products
        o["sapo_order_dto"] = order_dto
        
        filtered_orders.append(o)

    convert_time = time.time() - step_start
    variant_api_calls_during_convert = api_call_count["get_variant"] - variant_api_calls_before
    logger.info(f"[PERF] sapo_orders: Converted {len(filtered_orders)} orders in {convert_time:.2f}s "
                f"(errors: {convert_errors}, variant API calls: {variant_api_calls_during_convert})")
    debug_print(f"sapo_orders Converted {len(filtered_orders)} orders in {convert_time:.2f}s "
                f"(errors: {convert_errors}, variant API calls: {variant_api_calls_during_convert})")

    # Tổng kết
    total_time = time.time() - start_time
    logger.info(f"[PERF] sapo_orders: TOTAL TIME: {total_time:.2f}s | "
                f"API calls: list_orders={api_call_count['list_orders']}, get_variant={api_call_count['get_variant']} | "
                f"Orders: fetched={len(all_orders)}, converted={len(filtered_orders)}, errors={convert_errors}")
    debug_print(f"sapo_orders TOTAL TIME: {total_time:.2f}s | "
                f"API calls: list_orders={api_call_count['list_orders']}, get_variant={api_call_count['get_variant']} | "
                f"Orders: fetched={len(all_orders)}, converted={len(filtered_orders)}, errors={convert_errors}")

    context["orders"] = filtered_orders[::-1]
    context["current_kho"] = current_kho

    return render(request, "kho/orders/sapo_orders.html", context)




@group_required("WarehousePacker", "WarehouseManager")
def packing_orders(request):
    """
    Đóng gói hàng:
    - Scan barcode đơn hàng -> bắn đơn
    - Xem danh sách sản phẩm (visual check, không cần scan từng sản phẩm)
    - Đảm bảo tính chính xác của đơn hàng
    - Lưu thông tin: người gói, time gói (phục vụ KPI và rà soát camera)
    """
    from kho.models import WarehousePackingSetting
    from django.shortcuts import render
    
    # Kiểm tra quyền truy cập tính năng packing
    is_allowed, reason = WarehousePackingSetting.is_packing_enabled_for_user(request.user)
    
    if not is_allowed:
        # Render trang thông báo không có quyền
        context = {
            "title": "Không có quyền truy cập",
            "message": f"Bạn không thể sử dụng tính năng này. {reason}",
            "current_kho": request.session.get("current_kho", "geleximco"),
        }
        return render(request, "core/permission_denied.html", context, status=403)
    
    # Lấy first_name của user, nếu không có thì dùng username
    packer_name = request.user.first_name or request.user.username
    packer_username = request.user.username  # Dùng cho ảnh avatar
    
    context = {
        "title": "Đóng Gói Hàng - GIA DỤNG PLUS",
        "current_kho": request.session.get("current_kho", "geleximco"),
        "packer_name": packer_name,
        "packer_username": packer_username,
    }
    return render(request, "kho/orders/packing_orders.html", context)


@group_required("WarehouseManager")
def connect_shipping(request):
    """
    Liên kết đơn gửi bù:
    - Liên kết các đơn gửi bù cho khách với các đơn Shopee hiện tại
    - Ví dụ: khách A đặt đơn B bị thiếu sản phẩm C, sau khi khách đặt đơn mới thì gửi kèm sản phẩm C
    - Phải tạo đơn để liên kết (xuất kho, giao hàng, thông tin)
    """
    context = {
        "title": "Liên Kết Đơn Gửi Bù - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Logic liên kết đơn gửi bù
    return render(request, "kho/orders/connect_shipping.html", context)


@group_required("WarehouseManager")
def sos_shopee(request):
    """
    SOS Shopee:
    - Quản lý, rà soát trạng thái các đơn hàng đang cần xử lý tại kho (chưa xuất kho, đang cần xử lý)
    - Bao gồm đơn Shopee / đơn Sapo (trừ đơn hoả tốc)
    - 3 trạng thái: chưa xử lý, đã in/chưa gói, đã gói/chưa ship
    - Sắp xếp từ đơn gấp nhất (thời gian tạo đơn xa nhất đến gần nhất)
    """
    start_time = time.time()
    api_call_count = {"marketplace": 0, "sapo_core": 0, "get_order": 0}
    
    context = {
        "title": "SOS Shopee - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    
    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)
    
    # Service layer
    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()
    
    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)
    
    all_orders = []
    
    # ========== 1. LẤY ĐƠN TỪ MARKETPLACE (SHOPEE) ==========
    debug_print("sos_shopee Fetching Marketplace orders...")
    mp_orders = []
    page = 1
    limit = 250
    
    while True:
        mp_filter = BaseFilter(params={
            "connectionIds": connection_ids,
            "page": page,
            "limit": limit,
            "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED",
            "shippingCarrierIds": "51237,1218211,68301,36287,1218210,4110,59778,3411,1236070,37407,171067,1270129,57740,1236040,55646,166180,1289173,4095",
            "sortBy": "ISSUED_AT",
            "orderBy": "desc",
        })
        
        mp_resp = mp_service.list_orders(mp_filter)
        api_call_count["marketplace"] += 1
        orders = mp_resp.get("orders", [])
        metadata = mp_resp.get("metadata", {})
        total = metadata.get("total", 0)
        
        mp_orders.extend(orders)
        
        if not orders or len(mp_orders) >= total:
            break
        
        page += 1
    
    debug_print(f"sos_shopee Fetched {len(mp_orders)} Marketplace orders")
    
    # ========== OPTIMIZATION: Pre-fetch orders từ Sapo Core API để cache ==========
    step_start = time.time()
    debug_print("sos_shopee Pre-fetching recent orders from Sapo Core API to cache...")
    logger.info(f"[PERF] sos_shopee: Pre-fetching recent orders to cache...")
    
    # Collect tất cả sapo_order_ids cần fetch từ mp_orders
    sapo_order_ids = set()
    for o in mp_orders:
        sapo_order_id = o.get("sapo_order_id")
        if sapo_order_id:
            sapo_order_ids.add(sapo_order_id)
    
    debug_print(f"sos_shopee Need to fetch {len(sapo_order_ids)} unique orders")
    
    # Fetch list orders từ Sapo Core API (1000 orders gần nhất = 4 pages)
    orders_cache: Dict[int, Dict[str, Any]] = {}  # {order_id: raw_order_data}
    cache_fetch_start = time.time()
    page = 1
    limit = 250
    max_pages = 4  # 4 pages = 1000 orders
    
    cache_api_calls = 0
    while page <= max_pages:
        try:
            filters = {
                "status": "draft,finalized",  # Lấy cả draft và finalized
                "limit": limit,
                "page": page,
            }
            
            # Thêm location_id filter nếu có
            if allowed_location_id:
                filters["location_id"] = allowed_location_id
            
            page_start = time.time()
            raw_response = core_service._core_api.list_orders_raw(**filters)
            cache_api_calls += 1
            page_time = time.time() - page_start
            logger.info(f"[PERF] sos_shopee: Cache fetch page {page} took {page_time:.2f}s")
            
            orders_data = raw_response.get("orders", [])
            
            if not orders_data:
                break
            
            # Cache orders vào dict
            for order_data in orders_data:
                order_id = order_data.get("id")
                if order_id and order_id in sapo_order_ids:
                    orders_cache[order_id] = order_data
            
            debug_print(f"sos_shopee Cache page {page}: {len(orders_data)} orders, matched {len([o for o in orders_data if o.get('id') in sapo_order_ids])} needed orders")
            
            # Check nếu đã cache đủ orders cần thiết
            if len(orders_cache) >= len(sapo_order_ids):
                debug_print(f"sos_shopee Cache complete: {len(orders_cache)}/{len(sapo_order_ids)} orders found")
                break
            
            page += 1
        except Exception as e:
            logger.error(f"sos_shopee Error fetching cache page {page}: {e}", exc_info=True)
            break
    
    cache_fetch_time = time.time() - cache_fetch_start
    cache_hits = len(orders_cache)
    cache_misses = len(sapo_order_ids) - cache_hits
    debug_print(f"sos_shopee Cache fetch complete: {cache_hits} hits, {cache_misses} misses in {cache_fetch_time:.2f}s ({cache_api_calls} API calls)")
    logger.info(f"[PERF] sos_shopee: Cache fetch complete: {cache_hits} hits, {cache_misses} misses in {cache_fetch_time:.2f}s")
    
    # ========== 2. LẤY ĐƠN TỪ SAPO CORE (SAPO ORDERS) ==========
    debug_print("sos_shopee Fetching Sapo Core orders...")
    from core.sapo_client import get_sapo_client
    from orders.services.order_builder import OrderDTOFactory
    
    sapo = get_sapo_client()
    factory = OrderDTOFactory()
    
    sapo_orders_raw = []
    page = 1
    max_pages = 10
    
    while page <= max_pages:
        try:
            filters = {
                "status": "finalized",
                "composite_fulfillment_status": "wait_to_pack,packed_processing,packed",
                "limit": limit,
                "page": page,
            }
            
            if allowed_location_id:
                filters["location_id"] = allowed_location_id
            
            raw_response = sapo.core.list_orders_raw(**filters)
            api_call_count["sapo_core"] += 1
            orders_data = raw_response.get("orders", [])
            
            if not orders_data:
                break
            
            sapo_orders_raw.extend(orders_data)
            page += 1
        except Exception as e:
            logger.error(f"sos_shopee Error fetching Sapo Core page {page}: {e}", exc_info=True)
            break
    
    debug_print(f"sos_shopee Fetched {len(sapo_orders_raw)} Sapo Core orders")
    
    # ========== 3. XỬ LÝ MARKETPLACE ORDERS ==========
    for o in mp_orders:
        if not o.get("sapo_order_id"):
            continue
        
        # Lọc bỏ đơn hoả tốc
        shipping_carrier = (o.get("shipping_carrier_name") or "").lower()
        is_express = (
            "trong ngày" in shipping_carrier
            or "giao trong ngày" in shipping_carrier
            or "hoả tốc" in shipping_carrier
            or "hoa toc" in shipping_carrier
            or "grab" in shipping_carrier
            or "bedelivery" in shipping_carrier
            or "be delivery" in shipping_carrier
            or "ahamove" in shipping_carrier
            or "instant" in shipping_carrier
        )
        if is_express:
            continue
        
        try:
            # Check cache trước
            sapo_order_id = o["sapo_order_id"]
            if sapo_order_id in orders_cache:
                # Dùng data từ cache
                cached_data = orders_cache[sapo_order_id]
                debug_print(f"sos_shopee Using cached data for order {sapo_order_id}")
                order_dto: OrderDTO = build_order_from_sapo(cached_data, sapo_client=core_service._sapo)
            else:
                # Không có trong cache, gọi API riêng lẻ
                debug_print(f"sos_shopee Cache miss, calling API: GET /orders/{sapo_order_id}.json")
                order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
                api_call_count["get_order"] += 1
        except Exception as e:
            debug_print(f"sos_shopee Skip order {o.get('id')} - Error getting DTO: {e}")
            continue
        
        # Lọc theo kho
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue
        
        # Chỉ lấy đơn chưa ship
        if order_dto.fulfillment_status == "shipped":
            continue
        
        # Tính thời gian tạo đơn
        ts = o.get("created_at", 0) or 0
        dt = datetime.fromtimestamp(ts, tz_vn)
        
        # Phân loại trạng thái
        packing_status = order_dto.packing_status or 0
        if packing_status == 0:
            status_label = "Chưa xử lý"
            status_class = "bg-yellow-50 text-yellow-700 border-yellow-300"
        elif packing_status == 3:
            status_label = "Đã in / Chưa gói"
            status_class = "bg-orange-50 text-orange-700 border-orange-300"
        elif packing_status == 4:
            status_label = "Đã gói / Chưa ship"
            status_class = "bg-blue-50 text-blue-700 border-blue-300"
        else:
            status_label = "Khác"
            status_class = "bg-gray-50 text-gray-700 border-gray-300"
        
        # Lấy thông tin vận chuyển
        shipment_name = None
        tracking_code = None
        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                shipment_name = last_f.shipment.service_name
                tracking_code = last_f.shipment.tracking_code
        
        # Tính thời gian còn lại từ deadline
        deadline_remaining = ""
        deadline_delivery_text = ""
        if order_dto.ship_deadline_fast:
            deadline_dt = order_dto.ship_deadline_fast
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=tz_vn)
            elif deadline_dt.tzinfo != tz_vn:
                deadline_dt = deadline_dt.astimezone(tz_vn)
            
            remaining_seconds = (deadline_dt - now_vn).total_seconds()
            if remaining_seconds < 0:
                deadline_remaining = "Quá hạn"
                deadline_delivery_text = ""
            elif remaining_seconds < 3600:
                minutes = int(remaining_seconds // 60)
                deadline_remaining = f"Còn {minutes} phút"
                deadline_delivery_text = f"Bàn giao trong {minutes} phút"
            elif remaining_seconds < 86400:
                hours = int(remaining_seconds // 3600)
                deadline_remaining = f"Còn {hours} giờ"
                deadline_delivery_text = f"Bàn giao trong {hours} giờ"
            else:
                days = int(remaining_seconds // 86400)
                deadline_remaining = f"Còn {days} ngày"
                deadline_delivery_text = f"Bàn giao trong {days} ngày"
        
        # Gộp trạng thái với thông tin người gói
        if packing_status == 4 and order_dto.nguoi_goi:
            kho_label = "HN" if order_dto.location_id == 241737 else "SG"
            status_with_packer = f"{status_label} - {kho_label}: {order_dto.nguoi_goi}"
        else:
            status_with_packer = status_label
        
        # Lấy products với images
        from kho.services.product_service import get_variant_image
        products = []
        for line_item in order_dto.line_items[:4]:  # Chỉ lấy 4 sản phẩm đầu
            image_url = get_variant_image(line_item.variant_id) if line_item.variant_id else ""
            products.append({
                "sku": line_item.sku or "",
                "quantity": int(line_item.quantity) if line_item.quantity else 0,
                "image": image_url,
            })
        
        order_dict = {
            "id": o.get("id"),
            "sapo_order_id": order_dto.id,
            "sapo_order_code": order_dto.code,
            "channel_order_number": o.get("channel_order_number") or order_dto.reference_number or "",
            "sapo_channel": order_dto.channel or "Shopee",
            "shop_name": order_dto.shop_name or "",
            "shipping_carrier_name": shipment_name or o.get("shipping_carrier_name") or "",
            "tracking_code": tracking_code or "",
            "deadline": order_dto.ship_deadline_fast_str or "",
            "deadline_remaining": deadline_remaining,
            "deadline_delivery_text": deadline_delivery_text,
            "created_at": ts,
            "issued_dt": dt,
            "packing_status": packing_status,
            "status_label": status_label,
            "status_with_packer": status_with_packer,
            "status_class": status_class,
            "nguoi_goi": order_dto.nguoi_goi or "",
            "time_packing": order_dto.time_packing or "",
            "time_print": order_dto.time_print or "",
            "order_type": "marketplace",
            "location_id": order_dto.location_id,
            "products": products,
            "sapo_order_dto": order_dto,
        }
        
        # Tính thời gian đã trôi qua
        diff = now_vn - dt
        seconds = diff.total_seconds()
        if seconds < 60:
            order_dict["issued_ago"] = f"{int(seconds)} giây trước"
        elif seconds < 3600:
            order_dict["issued_ago"] = f"{int(seconds // 60)} phút trước"
        elif seconds < 86400:
            order_dict["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
        else:
            days = int(seconds // 86400)
            order_dict["issued_ago"] = f"{days} ngày trước"
        
        all_orders.append(order_dict)
    
    # ========== 4. XỬ LÝ SAPO CORE ORDERS ==========
    for raw_order in sapo_orders_raw:
        try:
            order_dto: OrderDTO = factory.from_sapo_json(raw_order, sapo_client=sapo)
        except Exception as e:
            debug_print(f"sos_shopee Skip order {raw_order.get('id')} - Error parsing DTO: {e}")
            continue
        
        # Lọc theo kho
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue
        
        # Chỉ lấy đơn ngoài sàn (bỏ qua đơn sàn TMĐT)
        if order_dto.is_marketplace_order:
            continue
        
        # Lọc bỏ đơn hoả tốc
        shipping_carrier = (order_dto.dvvc or "").lower()
        is_express = (
            "trong ngày" in shipping_carrier
            or "giao trong ngày" in shipping_carrier
            or "hoả tốc" in shipping_carrier
            or "hoa toc" in shipping_carrier
            or "grab" in shipping_carrier
            or "bedelivery" in shipping_carrier
            or "ahamove" in shipping_carrier
            or "instant" in shipping_carrier
        )
        if is_express:
            continue
        
        # Parse created_on
        created_dt = None
        if order_dto.created_on:
            try:
                created_dt = datetime.fromisoformat(order_dto.created_on.replace('Z', '+00:00'))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=tz_vn)
                if created_dt.tzinfo != tz_vn:
                    created_dt = created_dt.astimezone(tz_vn)
            except (ValueError, AttributeError):
                created_dt = None
        
        if not created_dt:
            continue
        
        # Phân loại trạng thái
        packing_status = order_dto.packing_status or 0
        if packing_status == 0:
            status_label = "Chưa xử lý"
            status_class = "bg-yellow-50 text-yellow-700 border-yellow-300"
        elif packing_status == 3:
            status_label = "Đã in / Chưa gói"
            status_class = "bg-orange-50 text-orange-700 border-orange-300"
        elif packing_status == 4:
            status_label = "Đã gói / Chưa ship"
            status_class = "bg-blue-50 text-blue-700 border-blue-300"
        else:
            status_label = "Khác"
            status_class = "bg-gray-50 text-gray-700 border-gray-300"
        
        # Lấy thông tin vận chuyển
        shipment_name = None
        tracking_code = None
        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                shipment_name = last_f.shipment.service_name
                tracking_code = last_f.shipment.tracking_code
        
        # Tính thời gian còn lại từ deadline
        deadline_remaining = ""
        deadline_delivery_text = ""
        if order_dto.ship_deadline_fast:
            deadline_dt = order_dto.ship_deadline_fast
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=tz_vn)
            elif deadline_dt.tzinfo != tz_vn:
                deadline_dt = deadline_dt.astimezone(tz_vn)
            
            remaining_seconds = (deadline_dt - now_vn).total_seconds()
            if remaining_seconds < 0:
                deadline_remaining = "Quá hạn"
                deadline_delivery_text = ""
            elif remaining_seconds < 3600:
                minutes = int(remaining_seconds // 60)
                deadline_remaining = f"Còn {minutes} phút"
                deadline_delivery_text = f"Bàn giao trong {minutes} phút"
            elif remaining_seconds < 86400:
                hours = int(remaining_seconds // 3600)
                deadline_remaining = f"Còn {hours} giờ"
                deadline_delivery_text = f"Bàn giao trong {hours} giờ"
            else:
                days = int(remaining_seconds // 86400)
                deadline_remaining = f"Còn {days} ngày"
                deadline_delivery_text = f"Bàn giao trong {days} ngày"
        
        # Gộp trạng thái với thông tin người gói
        if packing_status == 4 and order_dto.nguoi_goi:
            kho_label = "HN" if order_dto.location_id == 241737 else "SG"
            status_with_packer = f"{status_label} - {kho_label}: {order_dto.nguoi_goi}"
        else:
            status_with_packer = status_label
        
        # Lấy products với images
        from kho.services.product_service import get_variant_image
        products = []
        for line_item in order_dto.line_items[:4]:  # Chỉ lấy 4 sản phẩm đầu
            image_url = get_variant_image(line_item.variant_id) if line_item.variant_id else ""
            products.append({
                "sku": line_item.sku or "",
                "quantity": int(line_item.quantity) if line_item.quantity else 0,
                "image": image_url,
            })
        
        order_dict = {
            "id": order_dto.id,
            "sapo_order_id": order_dto.id,
            "sapo_order_code": order_dto.code,
            "channel_order_number": order_dto.reference_number or "",
            "sapo_channel": order_dto.channel or "Sapo",
            "shop_name": "",
            "shipping_carrier_name": shipment_name or order_dto.dvvc or "",
            "tracking_code": tracking_code or "",
            "deadline": order_dto.ship_deadline_fast_str or "",
            "deadline_remaining": deadline_remaining,
            "created_at": created_dt.timestamp(),
            "issued_dt": created_dt,
            "packing_status": packing_status,
            "status_label": status_label,
            "status_with_packer": status_with_packer,
            "status_class": status_class,
            "nguoi_goi": order_dto.nguoi_goi or "",
            "time_packing": order_dto.time_packing or "",
            "time_print": order_dto.time_print or "",
            "order_type": "sapo",
            "location_id": order_dto.location_id,
            "products": products,
            "sapo_order_dto": order_dto,
        }
        
        # Tính thời gian đã trôi qua
        diff = now_vn - created_dt
        seconds = diff.total_seconds()
        if seconds < 60:
            order_dict["issued_ago"] = f"{int(seconds)} giây trước"
        elif seconds < 3600:
            order_dict["issued_ago"] = f"{int(seconds // 60)} phút trước"
        elif seconds < 86400:
            order_dict["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
        else:
            days = int(seconds // 86400)
            order_dict["issued_ago"] = f"{days} ngày trước"
        
        all_orders.append(order_dict)
    
    # ========== 5. SẮP XẾP THEO THỜI GIAN TẠO ĐƠN (XA NHẤT ĐẾN GẦN NHẤT) ==========
    all_orders.sort(key=lambda x: x["created_at"])
    
    total_time = time.time() - start_time
    debug_print(f"sos_shopee TOTAL: {len(all_orders)} orders in {total_time:.2f}s")
    logger.info(f"[PERF] sos_shopee: {len(all_orders)} orders in {total_time:.2f}s | "
                f"API calls: marketplace={api_call_count['marketplace']}, sapo_core={api_call_count['sapo_core']}, get_order={api_call_count['get_order']}")
    
    context["orders"] = all_orders
    return render(request, "kho/orders/sos_shopee.html", context)


@group_required("WarehouseManager")
def packing_cancel(request):
    """
    Đơn đã gói nhưng bị huỷ:
    - Hiển thị danh sách các đơn đã gói (packing_status=4), nhưng trạng thái trên Sapo là Đã huỷ
    - Quản lý quá trình nhận lại hàng từ các đơn bị huỷ
    """
    start_time = time.time()
    api_call_count = {"sapo_core": 0}
    
    context = {
        "title": "Đã Gói, Bị Huỷ - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    
    # Giờ VN
    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)
    
    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)
    
    all_orders = []
    
    # ========== 1. LẤY ĐƠN TỪ SAPO CORE (SAPO ORDERS) ==========
    debug_print("packing_cancel Fetching Sapo Core cancelled orders...")
    from core.sapo_client import get_sapo_client
    from orders.services.order_builder import OrderDTOFactory
    
    sapo = get_sapo_client()
    factory = OrderDTOFactory()
    
    sapo_orders_raw = []
    page = 1
    limit = 250
    max_pages = 1
    
    while page <= max_pages:
        try:
            filters = {
                "status": "cancelled",
                "limit": limit,
                "page": page,
            }
            
            if allowed_location_id:
                filters["location_id"] = allowed_location_id
            
            raw_response = sapo.core.list_orders_raw(**filters)
            api_call_count["sapo_core"] += 1
            orders_data = raw_response.get("orders", [])
            
            if not orders_data:
                break
            
            sapo_orders_raw.extend(orders_data)
            page += 1
        except Exception as e:
            logger.error(f"packing_cancel Error fetching Sapo Core page {page}: {e}", exc_info=True)
            break
    
    debug_print(f"packing_cancel Fetched {len(sapo_orders_raw)} Sapo Core cancelled orders")
    
    # ========== 2. XỬ LÝ SAPO CORE ORDERS ==========
    for raw_order in sapo_orders_raw:
        try:
            order_dto: OrderDTO = factory.from_sapo_json(raw_order, sapo_client=sapo)
        except Exception as e:
            debug_print(f"packing_cancel Skip order {raw_order.get('id')} - Error parsing DTO: {e}")
            continue
        
        # Lọc theo kho
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue
        
        # CHỈ lấy đơn đã gói (packing_status = 4)
        if order_dto.packing_status != 4:
            continue
        
        # Lấy receive_cancel từ shipment note (từ raw order data)
        receive_cancel = 0
        try:
            # Lấy raw order để extract note từ shipment
            # get_order_raw() trả về {"order": {...}}, cần lấy từ key "order"
            raw_order_response = sapo.core.get_order_raw(order_dto.id)
            raw_order = raw_order_response.get("order") or raw_order_response
            
            if raw_order and raw_order.get("fulfillments"):
                last_fulfillment = raw_order["fulfillments"][-1]
                if last_fulfillment.get("shipment"):
                    shipment = last_fulfillment["shipment"]
                    note_str = shipment.get("note") or ""
                    if note_str and "{" in note_str:
                        from orders.services.sapo_service import mo_rong_gon
                        note_data = mo_rong_gon(note_str)
                        receive_cancel = note_data.get("receive_cancel") or note_data.get("rc") or 0
                        # Convert sang int để đảm bảo
                        try:
                            receive_cancel = int(receive_cancel)
                        except (ValueError, TypeError):
                            receive_cancel = 0
                        debug_print(f"packing_cancel Order {order_dto.id}: note={note_str[:100]}, receive_cancel={receive_cancel}")
        except Exception as e:
            debug_print(f"packing_cancel Error getting receive_cancel for order {order_dto.id}: {e}")
            receive_cancel = 0
        
        print(f"packing_cancel Order {order_dto.id}: receive_cancel={receive_cancel}")
        # Parse created_on
        created_dt = None
        if order_dto.created_on:
            try:
                created_dt = datetime.fromisoformat(order_dto.created_on.replace('Z', '+00:00'))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=tz_vn)
                if created_dt.tzinfo != tz_vn:
                    created_dt = created_dt.astimezone(tz_vn)
            except (ValueError, AttributeError):
                created_dt = None
        
        if not created_dt:
            continue
        
        # Lấy thông tin vận chuyển
        shipment_name = None
        tracking_code = None
        if order_dto.fulfillments:
            last_f = order_dto.fulfillments[-1]
            if last_f.shipment:
                shipment_name = last_f.shipment.service_name
                tracking_code = last_f.shipment.tracking_code
        
        # Lấy products với images
        from kho.services.product_service import get_variant_image
        products = []
        for line_item in order_dto.line_items[:4]:  # Chỉ lấy 4 sản phẩm đầu
            image_url = get_variant_image(line_item.variant_id) if line_item.variant_id else ""
            products.append({
                "sku": line_item.sku or "",
                "quantity": int(line_item.quantity) if line_item.quantity else 0,
                "image": image_url,
                "product_name": line_item.product_name or "",
            })
        
        order_dict = {
            "id": order_dto.id,
            "sapo_order_id": order_dto.id,
            "sapo_order_code": order_dto.code,
            "channel_order_number": order_dto.reference_number or "",
            "sapo_channel": order_dto.channel or "Sapo",
            "shop_name": "",
            "shipping_carrier_name": shipment_name or order_dto.dvvc or "",
            "tracking_code": tracking_code or "",
            "created_at": created_dt.timestamp(),
            "issued_dt": created_dt,
            "packing_status": 4,
            "receive_cancel": receive_cancel,
            "order_type": "sapo",
            "location_id": order_dto.location_id,
            "products": products,
            "sapo_order_dto": order_dto,
            "nguoi_goi": order_dto.nguoi_goi or "",
            "time_packing": order_dto.time_packing or "",
        }
        
        # Tính thời gian đã trôi qua
        diff = now_vn - created_dt
        seconds = diff.total_seconds()
        if seconds < 60:
            order_dict["issued_ago"] = f"{int(seconds)} giây trước"
        elif seconds < 3600:
            order_dict["issued_ago"] = f"{int(seconds // 60)} phút trước"
        elif seconds < 86400:
            order_dict["issued_ago"] = f"{int(seconds // 3600)} giờ trước"
        else:
            days = int(seconds // 86400)
            order_dict["issued_ago"] = f"{days} ngày trước"
        
        all_orders.append(order_dict)
    
    # ========== 2. SẮP XẾP THEO THỜI GIAN TẠO ĐƠN (XA NHẤT ĐẾN GẦN NHẤT) ==========
    all_orders.sort(key=lambda x: x["created_at"])
    
    total_time = time.time() - start_time
    debug_print(f"packing_cancel TOTAL: {len(all_orders)} orders in {total_time:.2f}s")
    logger.info(f"[PERF] packing_cancel: {len(all_orders)} orders in {total_time:.2f}s | "
                f"API calls: sapo_core={api_call_count['sapo_core']}")
    
    context["orders"] = all_orders
    return render(request, "kho/orders/packing_cancel.html", context)


@group_required("WarehouseManager")
def mark_received_cancel(request):
    """
    API endpoint để đánh dấu đã nhận lại hàng cho đơn bị huỷ.
    POST /kho/orders/packing_cancel/mark_received/
    Body: {"sapo_order_id": 123456}
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        sapo_order_id = int(data.get("sapo_order_id", 0))
        
        if not sapo_order_id:
            return JsonResponse({"error": "sapo_order_id is required"}, status=400)
        
        # Lấy order DTO
        core_service = SapoCoreOrderService()
        order_dto = core_service.get_order_dto(sapo_order_id)
        
        if not order_dto:
            return JsonResponse({"error": "Order not found"}, status=404)
        
        # Kiểm tra đơn có fulfillments không
        if not order_dto.fulfillments:
            return JsonResponse({"error": "Order has no fulfillments"}, status=400)
        
        # Lấy fulfillment cuối cùng
        last_f = order_dto.fulfillments[-1]
        if not last_f.shipment or not last_f.id:
            return JsonResponse({"error": "Order has no shipment"}, status=400)
        
        # Lấy fulfillment raw để update note (lấy từ API để có note đầy đủ nhất)
        from orders.services.sapo_service import mo_rong_gon, gopnhan_gon
        from core.sapo_client import get_sapo_client
        
        sapo = get_sapo_client()
        
        # Get fulfillment để lấy note hiện tại
        fulfillment_url = f"shipments/{last_f.id}.json"
        fulfillment_result = sapo.core.get(fulfillment_url)
        
        if not fulfillment_result or "fulfillment" not in fulfillment_result:
            return JsonResponse({"error": "Fulfillment not found"}, status=404)
        
        fulfillment = fulfillment_result["fulfillment"]
        shipment = fulfillment.get("shipment")
        
        if not shipment:
            return JsonResponse({"error": "Order has no shipment"}, status=400)
        
        # Lấy note hiện tại từ fulfillment và parse
        note_data = {}
        current_note = shipment.get("note") or ""
        
        if current_note and "{" in current_note:
            try:
                note_data = mo_rong_gon(current_note)
                logger.debug(f"[mark_received_cancel] Current note data: {note_data}")
            except Exception as e:
                logger.warning(f"[mark_received_cancel] Error parsing note: {e}")
                note_data = {}
        
        # Thêm receive_cancel = 1 vào note hiện có (không ghi đè)
        note_data["receive_cancel"] = 1
        
        # Nén và lưu lại
        compressed = gopnhan_gon(note_data)
        new_note = json.dumps(compressed, ensure_ascii=False, separators=(',', ':'))
        
        logger.debug(f"[mark_received_cancel] New note: {new_note}")
        
        # Update note trong fulfillment
        fulfillment["shipment"]["note"] = new_note
        
        # PUT update
        update_url = f"orders/{order_dto.id}/fulfillments/{last_f.id}.json"
        update_result = sapo.core.put(
            update_url,
            json={"fulfillment": fulfillment}
        )
        
        if update_result:
            logger.info(f"[packing_cancel] Marked received for order {sapo_order_id}")
            return JsonResponse({"success": True, "message": "Đã đánh dấu nhận lại hàng thành công"})
        
        return JsonResponse({"error": "Failed to update shipment note"}, status=500)
        
    except ValueError as e:
        return JsonResponse({"error": f"Invalid sapo_order_id: {e}"}, status=400)
    except Exception as e:
        logger.error(f"[packing_cancel] Error marking received: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@group_required("WarehouseManager")
def return_orders(request):
    """
    Quản lý đơn hoàn:
    - Quản lý các đơn hàng hoàn
    - Qui trình nhận hàng hoàn
    - Quản lý tình trạng khiếu nại, hỏng vỡ của các đơn hoàn này
    """
    context = {
        "title": "Hàng Hoàn - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Logic lấy đơn hoàn từ Sapo
    return render(request, "kho/orders/return_orders.html", context)


@group_required("WarehouseManager")
def pickup_orders(request):
    """
    Đơn pickup:
    - Đơn đã đóng gói, chờ đơn vị vận chuyển đến lấy
    """
    # TODO: gọi service lấy đơn trạng thái 'chờ lấy hàng'
    context = {
        "title": "Pick up",
        "orders": [],
    }
    return render(request, "kho/orders/pickup.html", context)


def _process_single_order(
    mp_order_id: int,
    meta: Dict[str, Any],
    core_service: SapoCoreOrderService,
    debug_mode: bool,
    BILL_DIR: str,
) -> Dict[str, Any]:
    """
    Xử lý một đơn hàng đơn lẻ.
    Thu thập log vào một string, chỉ in ra khi có lỗi.
    """
    """
    Xử lý một đơn hàng riêng lẻ - tạo PDF, lưu file, update packing status.
    
    Returns:
        Dict với keys:
            - "success": bool
            - "pdf_bytes": bytes | None
            - "channel_order_number": str
            - "error": Dict | None
            - "bill_path": str
    """
    result = {
        "success": False,
        "pdf_bytes": None,
        "channel_order_number": "",
        "error": None,
        "bill_path": "",
    }
    
    # Thu thập log vào một string
    log_messages = []
    
    def add_log(msg: str):
        """Thêm log message vào list"""
        if debug_mode:
            log_messages.append(msg)
    
    # Tắt các log từ các service khác khi xử lý đơn hàng
    # Chỉ bật lại khi có lỗi
    from orders.services import promotion_service, shopee_print_service
    from orders.services import sapo_service
    
    # Lưu trạng thái DEBUG ban đầu
    original_promo_debug = hasattr(promotion_service, 'debug_print')
    original_shopee_debug = shopee_print_service.DEBUG if hasattr(shopee_print_service, 'DEBUG') else True
    original_sapo_debug = sapo_service.DEBUG_PRINT if hasattr(sapo_service, 'DEBUG_PRINT') else True
    
    # Tắt log tạm thời (chỉ nếu không phải debug mode)
    def disable_logs():
        if hasattr(promotion_service, 'debug_print'):
            promotion_service.debug_print = lambda *args, **kwargs: None
        if hasattr(shopee_print_service, 'DEBUG'):
            # Chỉ tắt debug nếu không phải debug mode
            if not debug_mode:
                shopee_print_service.DEBUG = False
            else:
                # Nếu debug mode, đảm bảo DEBUG = True
                shopee_print_service.DEBUG = True
        if hasattr(sapo_service, 'DEBUG_PRINT'):
            sapo_service.DEBUG_PRINT = False
    
    def restore_logs():
        if hasattr(promotion_service, 'debug_print') and original_promo_debug:
            promotion_service.debug_print = print
        if hasattr(shopee_print_service, 'DEBUG'):
            shopee_print_service.DEBUG = original_shopee_debug
        if hasattr(sapo_service, 'DEBUG_PRINT'):
            sapo_service.DEBUG_PRINT = original_sapo_debug
    
    # Tắt log khi bắt đầu xử lý
    disable_logs()
    
    try:
        channel_order_number = meta["channel_order_number"]
        connection_id = meta["connection_id"]
        result["channel_order_number"] = channel_order_number
        
        # Kiểm tra nếu là đơn vị "Nhanh" (shippingCarrierIds=59778) -> sync đơn trước
        shipping_carrier_name = meta.get("shipping_carrier", "") or ""
        shipping_carrier_id = meta.get("shipping_carrier_id")
        
        # Check nếu là đơn vị "Nhanh" (ID=59778 hoặc tên chứa "Nhanh")
        is_nhanh_carrier = (
            shipping_carrier_id == 59778 
            or "nhanh" in shipping_carrier_name.lower()
        )
        
        if is_nhanh_carrier:
            try:
                # Gửi PUT request sync đơn
                from core.sapo_client import get_sapo_client
                sapo = get_sapo_client()
                sync_url = f"https://market-place.sapoapps.vn/v2/orders/sync?ids={mp_order_id}&accountId=319911"
                sapo.tmdt_session.put(sync_url)
                add_log(f"🔄 Synced order {channel_order_number} (Nhanh carrier)")
                # Đợi 0.5 giây
                time.sleep(0.5)
            except Exception as sync_err:
                add_log(f"⚠️ Sync order {channel_order_number} failed: {sync_err}")
        
        # Lấy DTO và apply gifts
        dto = None
        try:
            dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
            
            # Apply gifts từ promotions
            if dto:
                try:
                    from core.sapo_client import get_sapo_client
                    from orders.services.promotion_service import PromotionService
                    
                    sapo_for_promo = get_sapo_client()
                    promo_service = PromotionService(sapo_for_promo)
                    dto = promo_service.apply_gifts_to_order(dto)
                    
                    if dto.gifts:
                        add_log(f"✓ Applied {len(dto.gifts)} gift(s) to order {channel_order_number}")
                except Exception as gift_err:
                    logger.warning(f"Failed to apply gifts for order {channel_order_number}: {gift_err}")
        except Exception as dto_err:
            add_log(f"⚠️ Could not get DTO for order {channel_order_number}: {dto_err}")
        
        # Check PROCESSED và thử đọc file cũ
        is_processed = False
        init_fail_reason = meta.get("init_fail_reason", "")
        if "PROCESSED" in init_fail_reason:
            is_processed = True
        
        pdf_bytes = None
        bill_path = os.path.join(BILL_DIR, f"{channel_order_number}.pdf")
        result["bill_path"] = bill_path
        
        # Nếu đã processed, thử đọc file cũ
        if is_processed and os.path.exists(bill_path):
            try:
                with open(bill_path, "rb") as f:
                    pdf_bytes = f.read()
            except Exception:
                pass
        
        # Nếu chưa có, generate PDF mới
        if not pdf_bytes:
            try:
                shipping_carrier = meta.get("shipping_carrier") or ""
                
                # Kiểm tra dto trước khi truyền vào
                if dto is None:
                    # Thử lấy lại DTO một lần nữa
                    try:
                        dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
                        if dto is None:
                            raise RuntimeError(f"Could not get OrderDTO for {channel_order_number}")
                    except Exception as dto_err:
                        raise RuntimeError(f"Failed to get OrderDTO for {channel_order_number}: {dto_err}")
                
                pdf_bytes = generate_label_pdf_for_channel_order(
                    connection_id=connection_id,
                    channel_order_number=channel_order_number,
                    shipping_carrier=shipping_carrier,
                    order_dto=dto,
                )
            except Exception as e:
                # Import requests để check timeout
                import requests
                
                # Nếu là timeout, bỏ qua ngay không cần thử đọc file cũ
                is_timeout = (
                    isinstance(e, requests.Timeout) or 
                    isinstance(e, requests.exceptions.Timeout) or
                    "timeout" in str(e).lower() or 
                    "timed out" in str(e).lower()
                )
                
                if is_timeout:
                    error_reason = "generate_label_pdf_timeout"
                    result["error"] = {
                        "mp_order_id": mp_order_id,
                        "channel_order_number": channel_order_number,
                        "connection_id": connection_id,
                        "reason": error_reason,
                        "exception": str(e),
                    }
                    add_log(f"⏭️ Skipping order {channel_order_number} - timeout (skipping retry to speed up)")
                    # Bật lại log khi có lỗi
                    restore_logs()
                    # In log khi có lỗi
                    if log_messages:
                        debug_print(f"[Order {channel_order_number}] " + " | ".join(log_messages))
                    return result
                
                # Fallback cho các lỗi khác: thử đọc file cũ
                if os.path.exists(bill_path):
                    try:
                        with open(bill_path, "rb") as f:
                            pdf_bytes = f.read()
                    except Exception:
                        pass
                
                if not pdf_bytes:
                    error_reason = "generate_label_pdf_failed"
                    result["error"] = {
                        "mp_order_id": mp_order_id,
                        "channel_order_number": channel_order_number,
                        "connection_id": connection_id,
                        "reason": error_reason,
                        "exception": str(e),
                        "traceback": traceback.format_exc() if debug_mode else "",
                    }
                    add_log(f"⚠️ Skipping order {channel_order_number} - {error_reason}: {str(e)}")
                    # Bật lại log khi có lỗi
                    restore_logs()
                    # In log khi có lỗi
                    if log_messages:
                        debug_print(f"[Order {channel_order_number}] " + " | ".join(log_messages))
                    return result
        
        # Kiểm tra PDF bytes hợp lệ
        if not pdf_bytes or len(pdf_bytes) == 0:
            result["error"] = {
                "mp_order_id": mp_order_id,
                "channel_order_number": channel_order_number,
                "reason": "pdf_bytes_empty_or_none",
                "exception": "PDF bytes is empty or None after generation",
            }
            add_log(f"❌ PDF bytes is empty for order {channel_order_number}")
            # Bật lại log khi có lỗi
            restore_logs()
            # In log khi có lỗi
            if log_messages:
                debug_print(f"[Order {channel_order_number}] " + " | ".join(log_messages))
            return result
        
        # Lưu file
        try:
            with open(bill_path, "wb") as f:
                f.write(pdf_bytes)
        except Exception as e:
            result["error"] = {
                "mp_order_id": mp_order_id,
                "channel_order_number": channel_order_number,
                "reason": "cannot_write_file",
                "exception": str(e),
                "traceback": traceback.format_exc() if debug_mode else "",
            }
            add_log(f"❌ Cannot write file for order {channel_order_number}: {str(e)}")
            # Bật lại log khi có lỗi
            restore_logs()
            # In log khi có lỗi
            if log_messages:
                debug_print(f"[Order {channel_order_number}] " + " | ".join(log_messages))
            return result
        
        # Đánh dấu thành công khi PDF đã được tạo và ghi file thành công
        result["success"] = True
        result["pdf_bytes"] = pdf_bytes
        
        # KHÔNG gửi packing_status ở đây nữa
        # packing_status sẽ được gửi SAU KHI PDF đã được merge thành công vào file cuối cùng
        # Điều này đảm bảo không có đơn nào được đánh dấu thành công trên Sapo nếu PDF không được merge
        
        # Nếu thành công, KHÔNG in log nhưng vẫn restore logs để không ảnh hưởng đơn hàng tiếp theo
        restore_logs()
        
        return result
        
    except Exception as e:
        result["error"] = {
            "mp_order_id": mp_order_id,
            "channel_order_number": result.get("channel_order_number", ""),
            "reason": "unexpected_error",
            "exception": str(e),
            "traceback": traceback.format_exc() if debug_mode else "",
        }
        add_log(f"❌ Unexpected error for order {result.get('channel_order_number', mp_order_id)}: {str(e)}")
        # Bật lại log khi có lỗi
        restore_logs()
        # In log khi có lỗi
        if log_messages:
            debug_print(f"[Order {result.get('channel_order_number', mp_order_id)}] " + " | ".join(log_messages))
        return result


def _process_order_batch(
    batch_order_ids: List[int],
    order_meta: Dict[int, Dict[str, Any]],
    core_service: SapoCoreOrderService,
    debug_mode: bool,
    BILL_DIR: str,
    batch_num: int,
) -> Dict[str, Any]:
    """
    Xử lý một batch các đơn hàng (5 đơn).
    
    Returns:
        Dict với keys:
            - "batch_num": int
            - "results": List[Dict] - kết quả từ _process_single_order
            - "errors": List[Dict] - các lỗi
    """
    batch_result = {
        "batch_num": batch_num,
        "results": [],
        "errors": [],
    }
    
    for mp_order_id in batch_order_ids:
        meta = order_meta.get(mp_order_id)
        if not meta:
            batch_result["errors"].append({
                "mp_order_id": mp_order_id,
                "reason": "order_meta_not_found",
            })
            continue
        
        result = _process_single_order(
            mp_order_id=mp_order_id,
            meta=meta,
            core_service=core_service,
            debug_mode=debug_mode,
            BILL_DIR=BILL_DIR,
        )
        # Thêm mp_order_id và meta vào result để track sau khi merge
        result["mp_order_id"] = mp_order_id
        result["meta"] = meta
        
        if result.get("success"):
            channel_order_number = result.get("channel_order_number", "unknown")
            pdf_bytes = result.get("pdf_bytes")
            has_pdf = pdf_bytes is not None and len(pdf_bytes) > 0
            if debug_mode:
                debug_print(f"✅ Order {channel_order_number}: PDF generated successfully, size: {len(pdf_bytes) if pdf_bytes else 0} bytes")
            batch_result["results"].append(result)
        else:
            error_info = result.get("error", {})
            channel_order_number = result.get("channel_order_number", "unknown")
            reason = error_info.get("reason", "unknown")
            if debug_mode:
                debug_print(f"❌ Order {channel_order_number}: Failed - {reason}")
            batch_result["errors"].append(error_info)
    
    return batch_result


@require_GET
@group_required("WarehouseManager")
def print_now(request: HttpRequest):
    """
    /kho/orders/print_now/?ids=<list marketplace_id>&print=yes/no&debug=0/1&format=json

    - Nếu có format=json: xử lý và trả JSON với kết quả
    - Nếu không có format=json: render template với progress bar
    - JavaScript trong template sẽ gọi lại endpoint với format=json để lấy kết quả
    """

    ids_raw = request.GET.get("ids", "")
    do_print = request.GET.get("print", "no") == "yes"
    debug_mode = request.GET.get("debug", "1") in ("1", "true", "yes")  # Debug enabled by default
    format_json = request.GET.get("format") == "json"

    if not ids_raw:
        if format_json:
            return JsonResponse({"error": "missing ids"}, status=400)
        # Render template với lỗi
        context = {
            "title": "Đang xử lý phiếu in",
            "error": "Không có đơn hàng được chọn"
        }
        return render(request, "kho/orders/print_now.html", context)

    # Nếu không phải format=json, render template
    if not format_json:
        context = {
            "title": "Đang xử lý phiếu in",
        }
        return render(request, "kho/orders/print_now.html", context)

    try:
        order_ids: List[int] = [int(i.strip()) for i in ids_raw.split(",") if i.strip()]
    except ValueError:
        return JsonResponse({"error": "invalid ids"}, status=400)

    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()


    debug_info: Dict[str, Any] = {
        "order_ids": order_ids,
        "do_print": do_print,
        "step": "init_confirm_start",
    }

    # ------------------------------------------------------------------
    # B1: INIT_CONFIRM (chuẩn bị hàng) – luôn chạy
    # ------------------------------------------------------------------
    init_data: Dict[str, Any] | None = None
    order_meta: Dict[int, Dict[str, Any]] = {}  # {mp_order_id: {...}}

    try:
        init_data = mp_service.init_confirm(order_ids)
        debug_info["step"] = "init_confirm_done"
        if debug_mode:
            debug_info["init_raw"] = init_data
    except Exception as e:
        # Init lỗi:
        # - debug_mode: trả lỗi
        # - non-debug: bỏ qua init, vẫn cố gắng in (fallback get_order_detail)
        if debug_mode:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Lỗi khi init_confirm",
                    "exception": str(e),
                    "traceback": traceback.format_exc(),
                    "debug": debug_info,
                },
                status=500,
            )
        init_data = None  # không có init_data, chỉ còn fallback ở bước in

    confirm_items: List[MarketplaceConfirmOrderDTO] = []

    # ------------------------------------------------------------------
    # PHÂN TÍCH init_data -> tạo confirm_items + order_meta (nếu có init_data)
    # ------------------------------------------------------------------
    if init_data:
        try:
            data_root = init_data.get("data", {}) if isinstance(init_data, dict) else {}
            init_success_shopee = data_root.get("init_success", {}).get("shopee") or []
            init_fail_shopee = data_root.get("init_fail", {}).get("shopee") or []

            if debug_mode:
                debug_info["init_success_shopee_count"] = len(init_success_shopee)
                debug_info["init_fail_shopee_count"] = len(init_fail_shopee)

            # ---- 1) Lấy meta từ init_success (đơn confirm được) ----
            for shop_block in init_success_shopee:
                connection_id = shop_block["connection_id"]

                logistic = shop_block.get("logistic") or {}
                address_list = logistic.get("address_list") or []
                address_id = 0
                if address_list:
                    addr_obj = address_list[0]
                    address_id = int(addr_obj.get("address_id", 0) or 0)

                for item in shop_block.get("init_confirms", []):
                    mp_order_id = item["order_id"]
                    channel_order_number = item.get("channel_order_number")
                    shipping_carrier = (
                            item.get("shipping_by")
                            or item.get("shipping_carrier_name", "")
                    )
                    shipping_carrier_id = item.get("shipping_carrier_id") or item.get("shippingCarrierId")

                    pickup_time_id = None
                    models = item.get("pick_up_shopee_models") or []
                    if models and models[0].get("time_slot_list"):
                        pickup_time_id = models[0]["time_slot_list"][0]["pickup_time_id"]

                    # Xác định pick_up_type:
                    # - Đơn hoả tốc (SPX Express - Giao Trong Ngày, Ahamove - Giao trong ngày, Hoả Tốc - Trong ngày, etc.) 
                    #   -> LUÔN dùng pick_up_type = 1 (pickup - yêu cầu đơn vị vận chuyển tới lấy)
                    # - SPX Express thường + kho Hà Nội -> pick_up_type = 2 (dropoff - mang tới bưu cục)
                    # - Các trường hợp khác -> pick_up_type = 1 (pickup)
                    
                    shipping_carrier_lower = (shipping_carrier or "").lower()
                    is_express = (
                        "trong ngày" in shipping_carrier_lower
                        or "giao trong ngày" in shipping_carrier_lower
                        or "hoả tốc" in shipping_carrier_lower
                        or "hoa toc" in shipping_carrier_lower
                        or "grab" in shipping_carrier_lower
                        or "bedelivery" in shipping_carrier_lower
                        or "be delivery" in shipping_carrier_lower
                        or "ahamove" in shipping_carrier_lower
                        or "instant" in shipping_carrier_lower
                    )
                    
                    pick_up_type = 1  # Mặc định: pickup
                    if (
                            not is_express  # Không phải hoả tốc
                            and "SPX Express" in shipping_carrier
                            and address_id
                            and is_geleximco_address(address_id)
                    ):
                        # Chỉ SPX Express thường (không phải hoả tốc) + kho Hà Nội mới dùng dropoff
                        pick_up_type = 2

                    confirm_items.append(
                        MarketplaceConfirmOrderDTO(
                            connection_id=connection_id,
                            order_id=mp_order_id,
                            pickup_time_id=pickup_time_id,
                            pick_up_type=pick_up_type,
                            address_id=address_id or 0,
                        )
                    )

                    order_meta[mp_order_id] = {
                        "connection_id": connection_id,
                        "channel_order_number": channel_order_number,
                        "shipping_carrier": shipping_carrier,
                        "shipping_carrier_id": shipping_carrier_id,
                        "address_id": address_id,
                        "source": "init_success",
                    }

            # ---- 2) Lấy meta từ init_fail (đơn PROCESSED, không confirm được nhưng vẫn in) ----
            for shop_block in init_fail_shopee:
                connection_id = shop_block["connection_id"]
                logistic = shop_block.get("logistic") or {}
                address_list = logistic.get("address_list") or []
                address_id = 0
                if address_list:
                    addr_obj = address_list[0]
                    address_id = int(addr_obj.get("address_id", 0) or 0)

                for item in shop_block.get("init_confirms", []):
                    mp_order_id = item["order_id"]
                    channel_order_number = item.get("channel_order_number")
                    shipping_carrier = (
                            item.get("shipping_by")
                            or item.get("shipping_carrier_name", "")
                    )
                    shipping_carrier_id = item.get("shipping_carrier_id") or item.get("shippingCarrierId")
                    reason = item.get("reason")

                    # Không thêm vào confirm_items vì can_confirm = False
                    # Nhưng vẫn lưu meta để IN.
                    if mp_order_id not in order_meta:
                        order_meta[mp_order_id] = {
                            "connection_id": connection_id,
                            "channel_order_number": channel_order_number,
                            "shipping_carrier": shipping_carrier,
                            "shipping_carrier_id": shipping_carrier_id,
                            "address_id": address_id,
                            "source": "init_fail",
                            "init_fail_reason": reason,
                        }

            debug_info["order_meta_from_init"] = order_meta
            debug_info["step"] = "build_confirm_items_done"

        except Exception as e:
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi phân tích init_data",
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )
            # Nếu phân tích init_data lỗi, bỏ qua confirm, nhưng vẫn cố in ở bước sau
            confirm_items = []

    # ------------------------------------------------------------------
    # B2: CONFIRM_ORDERS (chuẩn bị hàng) – chỉ chạy nếu có confirm_items
    # ------------------------------------------------------------------
    errors: List[Dict[str, Any]] = []
    confirm_resp: Dict[str, Any] | None = None

    if confirm_items:
        try:
            confirm_resp = mp_service.confirm_orders(confirm_items)
            debug_info["step"] = "confirm_orders_done"
            if debug_mode:
                debug_info["confirm_raw_response"] = confirm_resp
        except Exception as e:
            # Confirm lỗi:
            # - debug_mode: trả lỗi luôn
            # - non-debug: vẫn tiếp tục sang bước in
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi confirm_orders",
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )
            confirm_resp = None

        # Phân tích lỗi (nếu có confirm_resp)
        if isinstance(confirm_resp, dict):
            data = confirm_resp.get("data", {})
            for block in data.get("list_error", []):
                conn_id = block.get("connection_id")
                for o in block.get("order_list", []):
                    if not o.get("success"):
                        errors.append(
                            {
                                "connection_id": conn_id,
                                "channel_order_number": o.get("channel_order_number"),
                                "sapo_order_number": o.get("sapo_order_number"),
                                "error": o.get("error"),
                            }
                        )

    debug_info["step"] = "after_parse_confirm_errors"
    debug_info["errors"] = errors
    overall_status = "ok" if not errors else "error"

    # ------------------------------------------------------------------
    # Nếu format=json -> trả JSON với kết quả
    # ------------------------------------------------------------------
    if format_json:
        # Đếm số đơn thành công và thất bại
        total_orders = len(order_ids)
        success_count = total_orders - len(errors)
        failed_count = len(errors)
        
        return JsonResponse(
            {
                "status": overall_status,
                "total": total_orders,
                "success": success_count,
                "failed": failed_count,
                "requested_ids": order_ids,
                "errors": errors,
                "confirm_response": confirm_resp,
                "debug": debug_info if debug_mode else None,
            }
        )
    
    # ------------------------------------------------------------------
    # Nếu chỉ "tìm ship" -> trả JSON, KHÔNG in
    # ------------------------------------------------------------------
    if not do_print:
        return JsonResponse(
            {
                "status": overall_status,
                "requested_ids": order_ids,
                "errors": errors,
                "confirm_response": confirm_resp,
                "debug": debug_info if debug_mode else None,
            }
        )

    # ------------------------------------------------------------------
    # B3: IN ĐƠN – KHÔNG BỊ CHẶN BỞI LỖI confirm
    # ------------------------------------------------------------------

    os.makedirs(BILL_DIR, exist_ok=True)

    writer = PdfWriter()
    debug_info["step"] = "start_generate_pdf"
    debug_info["generated_files"] = []
    debug_info["pdf_errors"] = []
    
    # =====================================================================
    # XỬ LÝ ĐA LUỒNG - Chia đơn hàng thành các batch, mỗi batch 5 đơn
    # =====================================================================
    ORDERS_PER_BATCH = 5
    batches = []
    for i in range(0, len(order_ids), ORDERS_PER_BATCH):
        batch = order_ids[i:i + ORDERS_PER_BATCH]
        batches.append((i // ORDERS_PER_BATCH + 1, batch))
    
    total_batches = len(batches)
    debug_info["total_orders"] = len(order_ids)
    debug_info["total_batches"] = total_batches
    debug_info["orders_per_batch"] = ORDERS_PER_BATCH
    
    if debug_mode:
        debug_print(f"🚀 Starting multi-threaded processing: {len(order_ids)} orders in {total_batches} batches")
    
    # Thread-safe collections
    all_pdf_results = []  # List of successful PDF results
    all_errors = []  # List of errors
    lock = threading.Lock()
    
    # Xử lý song song các batch
    with ThreadPoolExecutor(max_workers=total_batches) as executor:
        futures = {}
        for batch_num, batch_order_ids in batches:
            future = executor.submit(
                _process_order_batch,
                batch_order_ids,
                order_meta,
                core_service,
                debug_mode,
                BILL_DIR,
                batch_num,
            )
            futures[future] = batch_num
        
        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                batch_result = future.result()
                
                with lock:
                    # Collect successful PDFs
                    all_pdf_results.extend(batch_result["results"])
                    # Collect errors
                    all_errors.extend(batch_result["errors"])
                
                if debug_mode:
                    success_count = len(batch_result["results"])
                    error_count = len(batch_result["errors"])
                    debug_print(f"✅ Batch {batch_num}/{total_batches} completed: {success_count} success, {error_count} errors")
            except Exception as e:
                with lock:
                    all_errors.append({
                        "reason": "batch_processing_failed",
                        "batch_num": batch_num,
                        "exception": str(e),
                        "traceback": traceback.format_exc() if debug_mode else "",
                    })
                if debug_mode:
                    debug_print(f"❌ Batch {batch_num}/{total_batches} failed: {e}")
    
    # Cập nhật debug_info
    debug_info["pdf_errors"] = all_errors
    debug_info["successful_orders"] = len(all_pdf_results)
    debug_info["failed_orders"] = len(all_errors)
    
    if debug_mode:
        debug_print(f"📊 Processing complete: {len(all_pdf_results)} success, {len(all_errors)} errors")
    
    # =====================================================================
    # MERGE TẤT CẢ PDF ĐÃ TẠO THÀNH CÔNG
    # =====================================================================
    successfully_merged_orders = []  # Track các đơn đã merge thành công để gửi packing_status
    total_pages_before_merge = len(writer.pages)  # Track số trang trước khi merge
    
    for result in all_pdf_results:
        pdf_bytes = result["pdf_bytes"]
        channel_order_number = result["channel_order_number"]
        bill_path = result["bill_path"]
        mp_order_id = result.get("mp_order_id")
        meta = result.get("meta", {})
        
        # Thêm bill_path vào generated_files
        debug_info["generated_files"].append(bill_path)
        
        # Merge PDF vào writer
        reader = None
        merge_success = False
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            pages_to_add = len(reader.pages)
            
            if pages_to_add == 0:
                if debug_mode:
                    debug_print(f"⚠️ PDF {channel_order_number} has 0 pages, skipping merge")
                continue
            
            for page in reader.pages:
                writer.add_page(page)
            
            merge_success = True  # Đánh dấu merge thành công
            
            if debug_mode:
                file_size_kb = len(pdf_bytes) / 1024
                total_pages_after = len(writer.pages)
                pages_added = total_pages_after - total_pages_before_merge
                debug_print(f"📄 Merged PDF: {channel_order_number} - {pages_to_add} pages added, total pages now: {total_pages_after}, {file_size_kb:.1f} KB")
                total_pages_before_merge = total_pages_after
        except Exception as e:
            error_info = {
                "channel_order_number": channel_order_number,
                "reason": "cannot_read_or_merge_pdf",
                "exception": str(e),
                "traceback": traceback.format_exc() if debug_mode else "",
            }
            debug_info["pdf_errors"].append(error_info)
            if debug_mode:
                debug_print(f"⚠️ Failed to merge PDF for {channel_order_number}: {str(e)}")
        finally:
            if reader is not None:
                del reader
        
        # CHỈ track các đơn đã merge thành công để gửi packing_status sau
        if merge_success and mp_order_id and meta:
            successfully_merged_orders.append({
                "mp_order_id": mp_order_id,
                "channel_order_number": channel_order_number,
                "meta": meta,
            })

    # ------------------------------------------------------------------
    # GỬI packing_status LÊN SAPO CHO CÁC ĐƠN ĐÃ MERGE THÀNH CÔNG
    # ------------------------------------------------------------------
    for merged_order in successfully_merged_orders:
        mp_order_id = merged_order["mp_order_id"]
        channel_order_number = merged_order["channel_order_number"]
        meta = merged_order["meta"]
        
        try:
            # Lấy DTO để update packing_status
            dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
            if dto and dto.fulfillments and len(dto.fulfillments) > 0:
                last_ff = dto.fulfillments[-1]
                if last_ff.id and dto.id:
                    current_packing_status = dto.packing_status or 0
                    if current_packing_status < 3:
                        shipping_carrier_name = meta.get("shipping_carrier") or ""
                        try:
                            # Format time_print: "HH:MM DD-MM-YYYY"
                            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
                            now_vn = datetime.now(tz_vn)
                            time_print = now_vn.strftime("%H:%M %d-%m-%Y")
                            
                            core_service.update_fulfillment_packing_status(
                                order_id=dto.id,
                                fulfillment_id=last_ff.id,
                                packing_status=3,
                                dvvc=shipping_carrier_name,
                                time_packing=time_print
                            )
                            if debug_mode:
                                debug_print(f"✅ Updated packing_status=3 for order {channel_order_number}")
                        except Exception as e:
                            if debug_mode:
                                debug_print(f"⚠️ Failed to update packing_status for {channel_order_number}: {e}")
        except Exception as e:
            if debug_mode:
                debug_print(f"⚠️ Error updating packing_status for {channel_order_number}: {e}")
    
    # ------------------------------------------------------------------
    # Nếu format=json -> trả JSON với kết quả (KHÔNG tạo PDF, chỉ thống kê)
    # ------------------------------------------------------------------
    if format_json:
        # Tính tổng số đơn thành công và thất bại (bao gồm cả PDF errors)
        total_orders = len(order_ids)
        pdf_success_count = len(all_pdf_results)
        pdf_failed_count = len(all_errors)
        
        # Kết hợp errors từ confirm và PDF generation
        all_errors_combined = errors.copy()
        for pdf_err in all_errors:
            if isinstance(pdf_err, dict):
                all_errors_combined.append(pdf_err)
        
        # KHÔNG tạo PDF khi format=json, chỉ trả về thống kê
        # PDF sẽ được lấy từ endpoint riêng /kho/orders/print_now/pdf/
        
        return JsonResponse(
            {
                "status": "ok" if pdf_success_count > 0 else "error",
                "total": total_orders,
                "success": pdf_success_count,
                "failed": pdf_failed_count,
                "requested_ids": order_ids,
                "errors": all_errors_combined,
                "confirm_response": confirm_resp,
                "debug": debug_info if debug_mode else None,
            }
        )

    # ------------------------------------------------------------------
    # Kết thúc: nếu không có page nào -> báo lỗi rõ ràng
    # ------------------------------------------------------------------
    if not writer.pages:
        if debug_mode:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Không tạo được PDF để in",
                    "reason": "no_pages_in_writer",
                    "debug": debug_info,
                },
                status=500,
            )
        return JsonResponse(
            {"status": "error", "message": "Không tạo được PDF để in"}, status=500
        )

    # Tối ưu: Tránh tạo copy không cần thiết với getvalue()
    # Sử dụng streaming response để giảm memory usage
    output_buffer = BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    
    # Lấy size để set Content-Length (tùy chọn, giúp browser biết trước)
    pdf_data = output_buffer.read()
    output_buffer.close()  # Giải phóng buffer sớm
    
    # Log kích thước và số trang để debug (nếu debug mode)
    total_pages_final = len(writer.pages)
    if debug_mode:
        file_size_mb = len(pdf_data) / (1024 * 1024)
        debug_print(f"📦 Final merged PDF: {total_pages_final} pages, {file_size_mb:.2f} MB ({len(pdf_data)} bytes)")
        debug_info["merged_pdf_size_bytes"] = len(pdf_data)
        debug_info["merged_pdf_size_mb"] = round(file_size_mb, 2)
        debug_info["total_pages_merged"] = total_pages_final
        debug_info["total_orders_merged"] = len(successfully_merged_orders)
    
    # Thêm header để browser biết số trang
    response["X-PDF-Total-Pages"] = str(total_pages_final)

    response = HttpResponse(
        pdf_data,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = 'inline; filename="shipping_labels.pdf"'
    response["Content-Length"] = str(len(pdf_data))  # Giúp browser biết trước kích thước
    response["Cache-Control"] = "no-store"
    return response


@group_required("WarehouseManager")
def print_now_pdf(request: HttpRequest):
    """
    Endpoint riêng để lấy PDF sau khi đã xử lý xong.
    /kho/orders/print_now/pdf/?ids=<list marketplace_id>&print=yes&format=json
    
    - Nếu format=json: trả JSON với thông tin chính xác về số đơn thành công/thất bại
    - Nếu không có format=json: trả PDF trực tiếp
    """
    logger.info(f"print_now_pdf called with ids: {request.GET.get('ids', '')}")
    
    try:
        ids_raw = request.GET.get("ids", "")
        do_print = request.GET.get("print", "no") == "yes"
        debug_mode = request.GET.get("debug", "1") in ("1", "true", "yes")
        format_json = request.GET.get("format") == "json"

        logger.info(f"print_now_pdf: ids_raw={ids_raw}, do_print={do_print}, debug_mode={debug_mode}")

        if not ids_raw:
            logger.warning("print_now_pdf: missing ids")
            return JsonResponse({"error": "missing ids"}, status=400)

        try:
            order_ids: List[int] = [int(i.strip()) for i in ids_raw.split(",") if i.strip()]
            logger.info(f"print_now_pdf: parsed {len(order_ids)} order IDs")
        except ValueError as e:
            logger.error(f"print_now_pdf: invalid ids format: {e}")
            return JsonResponse({"error": "invalid ids"}, status=400)
    except Exception as e:
        logger.error(f"Error in print_now_pdf (initialization): {str(e)}", exc_info=True)
        return JsonResponse({"error": f"Initialization error: {str(e)}"}, status=500)

    mp_service = SapoMarketplaceService()
    core_service = SapoCoreOrderService()

    debug_info: Dict[str, Any] = {
        "order_ids": order_ids,
        "do_print": do_print,
        "step": "init_confirm_start",
    }

    # ------------------------------------------------------------------
    # B1: INIT_CONFIRM (chuẩn bị hàng) – luôn chạy
    # ------------------------------------------------------------------
    init_data: Dict[str, Any] | None = None
    order_meta: Dict[int, Dict[str, Any]] = {}  # {mp_order_id: {...}}

    try:
        init_data = mp_service.init_confirm(order_ids)
        debug_info["step"] = "init_confirm_done"
        if debug_mode:
            debug_info["init_raw"] = init_data
    except Exception as e:
        if debug_mode:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Lỗi khi init_confirm",
                    "exception": str(e),
                    "traceback": traceback.format_exc(),
                    "debug": debug_info,
                },
                status=500,
            )
        init_data = None

    confirm_items: List[MarketplaceConfirmOrderDTO] = []

    # ------------------------------------------------------------------
    # PHÂN TÍCH init_data -> tạo confirm_items + order_meta (nếu có init_data)
    # ------------------------------------------------------------------
    if init_data:
        try:
            data_root = init_data.get("data", {}) if isinstance(init_data, dict) else {}
            init_success_shopee = data_root.get("init_success", {}).get("shopee") or []
            init_fail_shopee = data_root.get("init_fail", {}).get("shopee") or []

            if debug_mode:
                debug_info["init_success_shopee_count"] = len(init_success_shopee)
                debug_info["init_fail_shopee_count"] = len(init_fail_shopee)

            # ---- 1) Lấy meta từ init_success (đơn confirm được) ----
            for shop_block in init_success_shopee:
                connection_id = shop_block["connection_id"]
                logistic = shop_block.get("logistic") or {}
                address_list = logistic.get("address_list") or []
                address_id = 0
                if address_list:
                    addr_obj = address_list[0]
                    address_id = int(addr_obj.get("address_id", 0) or 0)

                for item in shop_block.get("init_confirms", []):
                    mp_order_id = item["order_id"]
                    channel_order_number = item.get("channel_order_number")
                    shipping_carrier = (
                            item.get("shipping_by")
                            or item.get("shipping_carrier_name", "")
                    )
                    shipping_carrier_id = item.get("shipping_carrier_id") or item.get("shippingCarrierId")

                    pickup_time_id = None
                    models = item.get("pick_up_shopee_models") or []
                    if models and models[0].get("time_slot_list"):
                        pickup_time_id = models[0]["time_slot_list"][0]["pickup_time_id"]

                    shipping_carrier_lower = (shipping_carrier or "").lower()
                    is_express = (
                        "trong ngày" in shipping_carrier_lower
                        or "giao trong ngày" in shipping_carrier_lower
                        or "hoả tốc" in shipping_carrier_lower
                        or "hoa toc" in shipping_carrier_lower
                        or "grab" in shipping_carrier_lower
                        or "bedelivery" in shipping_carrier_lower
                        or "be delivery" in shipping_carrier_lower
                        or "ahamove" in shipping_carrier_lower
                        or "instant" in shipping_carrier_lower
                    )
                    
                    pick_up_type = 1
                    if (
                            not is_express
                            and "SPX Express" in shipping_carrier
                            and address_id
                            and is_geleximco_address(address_id)
                    ):
                        pick_up_type = 2

                    confirm_items.append(
                        MarketplaceConfirmOrderDTO(
                            connection_id=connection_id,
                            order_id=mp_order_id,
                            pickup_time_id=pickup_time_id,
                            pick_up_type=pick_up_type,
                            address_id=address_id or 0,
                        )
                    )

                    order_meta[mp_order_id] = {
                        "connection_id": connection_id,
                        "channel_order_number": channel_order_number,
                        "shipping_carrier": shipping_carrier,
                        "shipping_carrier_id": shipping_carrier_id,
                        "address_id": address_id,
                        "source": "init_success",
                    }

            # ---- 2) Lấy meta từ init_fail (đơn PROCESSED, không confirm được nhưng vẫn in) ----
            for shop_block in init_fail_shopee:
                connection_id = shop_block["connection_id"]
                logistic = shop_block.get("logistic") or {}
                address_list = logistic.get("address_list") or []
                address_id = 0
                if address_list:
                    addr_obj = address_list[0]
                    address_id = int(addr_obj.get("address_id", 0) or 0)

                for item in shop_block.get("init_confirms", []):
                    mp_order_id = item["order_id"]
                    channel_order_number = item.get("channel_order_number")
                    shipping_carrier = (
                            item.get("shipping_by")
                            or item.get("shipping_carrier_name", "")
                    )
                    shipping_carrier_id = item.get("shipping_carrier_id") or item.get("shippingCarrierId")
                    reason = item.get("reason")

                    if mp_order_id not in order_meta:
                        order_meta[mp_order_id] = {
                            "connection_id": connection_id,
                            "channel_order_number": channel_order_number,
                            "shipping_carrier": shipping_carrier,
                            "shipping_carrier_id": shipping_carrier_id,
                            "address_id": address_id,
                            "source": "init_fail",
                            "init_fail_reason": reason,
                        }

            debug_info["order_meta_from_init"] = order_meta
            debug_info["step"] = "build_confirm_items_done"

        except Exception as e:
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi phân tích init_data",
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )
            confirm_items = []

    # ------------------------------------------------------------------
    # B2: CONFIRM_ORDERS (chuẩn bị hàng) – chỉ chạy nếu có confirm_items
    # ------------------------------------------------------------------
    if confirm_items:
        try:
            mp_service.confirm_orders(confirm_items)
            debug_info["step"] = "confirm_orders_done"
        except Exception as e:
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi confirm_orders",
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )

    # ------------------------------------------------------------------
    # B3: TẠO PDF
    # ------------------------------------------------------------------
    try:
        os.makedirs(BILL_DIR, exist_ok=True)
    except Exception as e:
        if debug_mode:
            debug_print(f"⚠️ Error creating BILL_DIR: {e}")
    
    writer = PdfWriter()
    debug_info["step"] = "start_generate_pdf"
    debug_info["generated_files"] = []
    debug_info["pdf_errors"] = []
    
    ORDERS_PER_BATCH = 5
    batches = []
    for i in range(0, len(order_ids), ORDERS_PER_BATCH):
        batch = order_ids[i:i + ORDERS_PER_BATCH]
        batches.append((i // ORDERS_PER_BATCH + 1, batch))
    
    total_batches = len(batches)
    debug_info["total_orders"] = len(order_ids)
    debug_info["total_batches"] = total_batches
    debug_info["orders_per_batch"] = ORDERS_PER_BATCH
    
    all_pdf_results = []
    all_errors = []
    lock = threading.Lock()
    
    with ThreadPoolExecutor(max_workers=total_batches) as executor:
        futures = {}
        for batch_num, batch_order_ids in batches:
            future = executor.submit(
                _process_order_batch,
                batch_order_ids,
                order_meta,
                core_service,
                debug_mode,
                BILL_DIR,
                batch_num,
            )
            futures[future] = batch_num
        
        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                batch_result = future.result()
                with lock:
                    results_count = len(batch_result["results"])
                    errors_count = len(batch_result["errors"])
                    all_pdf_results.extend(batch_result["results"])
                    all_errors.extend(batch_result["errors"])
                    if debug_mode:
                        debug_print(f"📦 Batch {batch_num}/{total_batches} completed: {results_count} PDFs, {errors_count} errors")
            except Exception as e:
                with lock:
                    all_errors.append({
                        "reason": "batch_processing_failed",
                        "batch_num": batch_num,
                        "exception": str(e),
                        "traceback": traceback.format_exc() if debug_mode else "",
                    })
                if debug_mode:
                    debug_print(f"❌ Batch {batch_num}/{total_batches} failed: {str(e)}")
    
    debug_info["pdf_errors"] = all_errors
    total_orders = len(order_ids)
    
    if debug_mode:
        debug_print(f"📊 Processing complete: {len(all_pdf_results)} PDFs generated, {len(all_errors)} errors")
    
    # Kiểm tra nếu không có PDF nào được tạo thành công
    if not all_pdf_results:
        if debug_mode:
            debug_print(f"⚠️ No PDFs were generated successfully. Total errors: {len(all_errors)}")
            logger.error(f"No PDFs generated. Errors: {all_errors}")
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Không tạo được PDF nào để in",
                    "reason": "no_pdf_results",
                    "errors": all_errors,
                    "debug": debug_info,
                },
                status=500,
            )
        logger.error(f"No PDFs generated. Errors: {all_errors}")
        return JsonResponse(
            {"status": "error", "message": "Không tạo được PDF nào để in"}, status=500
        )
    
    # Merge PDF và tính lại số đơn thành công/thất bại chính xác
    pdf_success_count = 0
    pdf_failed_count = len(all_errors)  # Bắt đầu với số lỗi đã có
    successfully_merged_orders = []  # Track các đơn đã merge thành công để gửi packing_status
    total_pages_before_merge = len(writer.pages)  # Track số trang trước khi merge
    
    for result in all_pdf_results:
        pdf_bytes = result.get("pdf_bytes")
        channel_order_number = result.get("channel_order_number", "unknown")
        bill_path = result.get("bill_path", "")
        mp_order_id = result.get("mp_order_id")
        meta = result.get("meta", {})
        
        if not pdf_bytes:
            if debug_mode:
                debug_print(f"⚠️ PDF bytes is None or empty for {channel_order_number}")
            pdf_failed_count += 1
            continue
        
        debug_info["generated_files"].append(bill_path)
        
        reader = None
        merge_success = False
        try:
            if debug_mode:
                debug_print(f"🔄 Attempting to merge PDF for {channel_order_number}, size: {len(pdf_bytes)} bytes")
            
            reader = PdfReader(BytesIO(pdf_bytes), strict=False)
            pages_to_add = len(reader.pages)
            
            if pages_to_add == 0:
                if debug_mode:
                    debug_print(f"⚠️ PDF {channel_order_number} has 0 pages, skipping merge")
                pdf_failed_count += 1
                continue
            
            if debug_mode:
                debug_print(f"📄 Adding {pages_to_add} pages from {channel_order_number} to writer")
            
            for page in reader.pages:
                writer.add_page(page)
            
            # Nếu merge thành công, tăng số đơn thành công
            pdf_success_count += 1
            merge_success = True
            
            if debug_mode:
                total_pages_after = len(writer.pages)
                file_size_kb = len(pdf_bytes) / 1024
                debug_print(f"✅ Merged PDF: {channel_order_number} - {pages_to_add} pages added, total pages now: {total_pages_after}, {file_size_kb:.1f} KB")
                total_pages_before_merge = total_pages_after
        except Exception as e:
            # Nếu merge thất bại, tăng số đơn thất bại
            pdf_failed_count += 1
            error_info = {
                "channel_order_number": channel_order_number,
                "reason": "cannot_read_or_merge_pdf",
                "exception": str(e),
                "traceback": traceback.format_exc() if debug_mode else "",
            }
            debug_info["pdf_errors"].append(error_info)
            all_errors.append(error_info)
            if debug_mode:
                debug_print(f"❌ Failed to merge PDF for {channel_order_number}: {str(e)}")
                debug_print(f"   Traceback: {traceback.format_exc()}")
            logger.error(f"Failed to merge PDF for {channel_order_number}: {str(e)}", exc_info=True)
        finally:
            if reader is not None:
                del reader
        
        # CHỈ track các đơn đã merge thành công để gửi packing_status sau
        if merge_success and mp_order_id and meta:
            successfully_merged_orders.append({
                "mp_order_id": mp_order_id,
                "channel_order_number": channel_order_number,
                "meta": meta,
            })
    
    # ------------------------------------------------------------------
    # GỬI packing_status LÊN SAPO CHO CÁC ĐƠN ĐÃ MERGE THÀNH CÔNG
    # ------------------------------------------------------------------
    for merged_order in successfully_merged_orders:
        mp_order_id = merged_order["mp_order_id"]
        channel_order_number = merged_order["channel_order_number"]
        meta = merged_order["meta"]
        
        try:
            # Lấy DTO để update packing_status
            dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
            if dto and dto.fulfillments and len(dto.fulfillments) > 0:
                last_ff = dto.fulfillments[-1]
                if last_ff.id and dto.id:
                    current_packing_status = dto.packing_status or 0
                    if current_packing_status < 3:
                        shipping_carrier_name = meta.get("shipping_carrier") or ""
                        try:
                            # Format time_print: "HH:MM DD-MM-YYYY"
                            tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
                            now_vn = datetime.now(tz_vn)
                            time_print = now_vn.strftime("%H:%M %d-%m-%Y")
                            
                            core_service.update_fulfillment_packing_status(
                                order_id=dto.id,
                                fulfillment_id=last_ff.id,
                                packing_status=3,
                                dvvc=shipping_carrier_name,
                                time_packing=time_print
                            )
                            if debug_mode:
                                debug_print(f"✅ Updated packing_status=3 for order {channel_order_number}")
                        except Exception as e:
                            if debug_mode:
                                debug_print(f"⚠️ Failed to update packing_status for {channel_order_number}: {e}")
        except Exception as e:
            if debug_mode:
                debug_print(f"⚠️ Error updating packing_status for {channel_order_number}: {e}")
    
    # Cập nhật debug_info với số liệu chính xác
    debug_info["successful_orders"] = pdf_success_count
    debug_info["failed_orders"] = pdf_failed_count
    
    if debug_mode:
        debug_print(f"📊 Merge summary: {pdf_success_count} orders merged successfully, {pdf_failed_count} failed")
        debug_print(f"📄 Total pages in writer: {len(writer.pages)}")
        debug_print(f"📋 Expected: {len(all_pdf_results)} PDFs, Got: {pdf_success_count} merged")
        if pdf_success_count < len(all_pdf_results):
            missing_count = len(all_pdf_results) - pdf_success_count
            debug_print(f"⚠️ WARNING: {missing_count} PDFs were NOT merged successfully!")
            debug_print(f"   This means {missing_count} orders will NOT appear in the final PDF!")

    if not writer.pages:
        if debug_mode:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Không tạo được PDF để in",
                    "reason": "no_pages_in_writer",
                    "debug": debug_info,
                },
                status=500,
            )
        return JsonResponse(
            {"status": "error", "message": "Không tạo được PDF để in"}, status=500
        )

    total_pages_final = len(writer.pages)
    
    if debug_mode:
        debug_print(f"📊 Before writing PDF: {total_pages_final} pages, {pdf_success_count} orders merged successfully")
    
    try:
        if debug_mode:
            debug_print(f"🔄 Starting to write PDF to buffer...")
        
        output_buffer = BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        pdf_data = output_buffer.read()
        output_buffer.close()
        
        if not pdf_data or len(pdf_data) == 0:
            raise ValueError("PDF data is empty after writing")
        
        if debug_mode:
            file_size_mb = len(pdf_data) / (1024 * 1024)
            debug_print(f"✅ PDF written successfully: {total_pages_final} pages, {file_size_mb:.2f} MB ({len(pdf_data)} bytes)")
            debug_info["merged_pdf_size_bytes"] = len(pdf_data)
            debug_info["merged_pdf_size_mb"] = round(file_size_mb, 2)
            debug_info["total_pages_merged"] = total_pages_final
            debug_info["total_orders_merged"] = len(successfully_merged_orders)

        if debug_mode:
            debug_print(f"🔄 Creating HTTP response...")
        
        response = HttpResponse(
            pdf_data,
            content_type="application/pdf",
        )
        response["Content-Disposition"] = 'inline; filename="shipping_labels.pdf"'
        response["Content-Length"] = str(len(pdf_data))
        response["Cache-Control"] = "no-store"
        response["X-PDF-Total-Pages"] = str(total_pages_final)
        response["X-PDF-Success-Count"] = str(pdf_success_count)
        response["X-PDF-Failed-Count"] = str(pdf_failed_count)
        response["X-PDF-Total-Count"] = str(len(order_ids))
        
        if debug_mode:
            debug_print(f"✅ HTTP response created successfully")
        
        return response
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        if debug_mode:
            debug_print(f"❌ Error writing PDF: {error_msg}")
            debug_print(f"   Traceback: {error_traceback}")
        
        # Log to Django logger as well
        logger.error(f"Error in print_now_pdf (writing PDF): {error_msg}", exc_info=True)
        
        if debug_mode:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Lỗi khi tạo PDF",
                    "exception": error_msg,
                    "traceback": error_traceback,
                    "debug": debug_info,
                },
                status=500,
            )
        return JsonResponse(
            {"status": "error", "message": f"Lỗi khi tạo PDF: {error_msg}"}, status=500
        )


@group_required("WarehousePacker")
def packing_board(request):
    """
    Màn hình packing:
    - Bảng điều khiển cho kho gói hàng
    - Có thể hiển thị cho từng nhân viên, từng line gói
    """
    context = {
        "title": "Packing",
        "orders": [],
    }
    return render(request, "kho/orders/packing.html", context)
