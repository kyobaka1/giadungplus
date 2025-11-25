# kho/views/orders.py
from typing import Any, Dict, List

from core.system_settings import get_connection_ids
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
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

from PyPDF2 import PdfReader, PdfWriter  # pip install PyPDF2
from orders.services.sapo_service import SapoMarketplaceService
from orders.services.dto import MarketplaceConfirmOrderDTO
from core.system_settings import is_geleximco_address
from orders.services.shopee_print_service import generate_label_pdf_for_channel_order, extract_customer_info
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET
import json
import logging

logger = logging.getLogger(__name__)

connection_ids = get_connection_ids()
LOCATION_BY_KHO = {
    "geleximco": 241737,  # HN
    "toky": 548744,       # HCM
}
BILL_DIR = "logs/bill"
DEBUG_PRINT_ENABLED = True

def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)

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

@login_required
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
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 50, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED","shippingCarrierIds":"134097,1285481,108346,17426,60176,1283785,1285470,35696,47741,14895,1272209,176002,4329", "sortBy": "ISSUED_AT", "orderBy": "desc", })

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

        # 2) Lấy Sapo core order (DTO) theo sapo_order_id
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


@login_required
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

        # 2) Lấy Sapo core order (DTO) theo sapo_order_id
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

        # 3) Lọc theo packing_status
        if order_dto.packing_status and order_dto.packing_status != 0:
            skipped_packed += 1
            debug_print(f"shopee_orders Skip order {o.get('id')} - Already packed (status={order_dto.packing_status})")
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

@login_required
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




@login_required
def packing_orders(request):
    """
    Đóng gói hàng:
    - Scan barcode đơn hàng -> bắn đơn
    - Scan barcode sản phẩm -> bắn sản phẩm
    - Đảm bảo tính chính xác của đơn hàng
    - Lưu thông tin: người gói, time gói (phục vụ KPI và rà soát camera)
    """
    context = {
        "title": "Đóng Gói Hàng - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Logic scan barcode đóng gói
    # TODO: API endpoint để handle scan barcode
    return render(request, "kho/orders/packing_orders.html", context)


@login_required
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


@login_required
def sos_shopee(request):
    """
    SOS Shopee:
    - Quản lý các trạng thái của đơn hàng
    - Phục vụ mục tiêu rà soát lại các đơn hàng cần xử lý và đã xử lý
    - Để kịp tiến độ SLA giao hàng của sàn
    - Ví dụ: để biết đơn nào đã in, chưa gói -> xử lý sót...
    """
    context = {
        "title": "SOS Shopee - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Logic lấy đơn có vấn đề (đã in nhưng chưa gói, etc.)
    return render(request, "kho/orders/sos_shopee.html", context)


@login_required
def packing_cancel(request):
    """
    Đơn đã gói nhưng bị huỷ:
    - Quản lý các đơn đã gói hàng nhưng bị huỷ ngang
    - Cần thu hồi lại đơn hàng
    - Theo dõi quá trình này tránh bị mất hàng
    """
    context = {
        "title": "Đã Gói Nhưng Bị Huỷ - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Logic lấy đơn đã packed nhưng bị cancelled
    return render(request, "kho/orders/packing_cancel.html", context)


@login_required
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


@login_required
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


@require_GET
def print_now(request: HttpRequest):
    """
    /kho/orders/print_now/?ids=<list marketplace_id>&print=yes/no&debug=0/1

    Ý tưởng mới:
    - Luôn gọi init_confirm trước để "tìm ship / chuẩn bị hàng".
    - Nếu có trong init_success -> confirm_orders như cũ.
    - Dù init_success hay init_fail, vẫn cố gắng in:
        + Lấy channel_order_number + connection_id từ init_confirm (nếu có).
        + Nếu không có (không nằm trong init_success/init_fail) -> fallback sang get_order_detail.
    - print=no  -> chỉ chạy init_confirm + confirm_orders, trả JSON.
    - print=yes -> init_confirm + confirm_orders, SAU ĐÓ luôn cố gắng generate PDF và trả về browser.
    """

    ids_raw = request.GET.get("ids", "")
    do_print = request.GET.get("print", "no") == "yes"
    debug_mode = request.GET.get("debug", "0") in ("1", "true", "yes")

    if not ids_raw:
        return JsonResponse({"error": "missing ids"}, status=400)

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

                    pickup_time_id = None
                    models = item.get("pick_up_shopee_models") or []
                    if models and models[0].get("time_slot_list"):
                        pickup_time_id = models[0]["time_slot_list"][0]["pickup_time_id"]

                    pick_up_type = 1
                    if (
                            "SPX Express" in shipping_carrier
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
                    reason = item.get("reason")

                    # Không thêm vào confirm_items vì can_confirm = False
                    # Nhưng vẫn lưu meta để IN.
                    if mp_order_id not in order_meta:
                        order_meta[mp_order_id] = {
                            "connection_id": connection_id,
                            "channel_order_number": channel_order_number,
                            "shipping_carrier": shipping_carrier,
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

    for mp_order_id in order_ids:
        # Lấy meta nếu đã có từ init_confirm
        meta = order_meta.get(mp_order_id)

        # Nếu chưa có (không nằm trong init_success / init_data bị lỗi) -> fallback get_order_detail
        meta = order_meta.get(mp_order_id)
        if not meta:
            debug_info["pdf_errors"].append(
                {
                    "mp_order_id": mp_order_id,
                    "reason": "order_meta_not_found_in_init_success_or_fail",
                }
            )
            # debug thì trả luôn cho dễ soi
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Không tìm thấy channel_order_number / connection_id cho đơn này trong init_success/init_fail",
                        "mp_order_id": mp_order_id,
                        "debug": debug_info,
                    },
                    status=500,
                )
            continue

        channel_order_number = meta["channel_order_number"]
        connection_id = meta["connection_id"]

        # --- Logic mới: Check PROCESSED hoặc fallback ---
        # 1. Check nếu đơn bị PROCESSED (init_fail) -> ưu tiên lấy từ file cũ
        is_processed = False
        init_fail_reason = meta.get("init_fail_reason", "")
        if "PROCESSED" in init_fail_reason:
            is_processed = True
        
        pdf_bytes = None
        bill_path = os.path.join(BILL_DIR, f"{channel_order_number}.pdf")

        # Nếu đã processed, thử đọc file cũ trước
        if is_processed and os.path.exists(bill_path):
            try:
                with open(bill_path, "rb") as f:
                    pdf_bytes = f.read()
                debug_info.setdefault("logs", []).append(f"Loaded from local log: {bill_path}")
            except Exception:
                pass

        # Nếu chưa có pdf_bytes (do không phải processed hoặc file không tồn tại), gọi API
        if not pdf_bytes:
            try:
                shipping_carrier = meta.get("shipping_carrier") or ""
                pdf_bytes = generate_label_pdf_for_channel_order(
                    connection_id=connection_id,
                    channel_order_number=channel_order_number,
                    shipping_carrier=shipping_carrier,
                )
            except Exception as e:
                # Fallback cuối cùng: thử đọc file log lần nữa (có thể do lỗi mạng nhưng file cũ vẫn còn)
                if os.path.exists(bill_path):
                    try:
                        with open(bill_path, "rb") as f:
                            pdf_bytes = f.read()
                        debug_info.setdefault("logs", []).append(f"Fallback to local log after error: {bill_path}")
                    except Exception:
                        pass
                
                if not pdf_bytes:
                    debug_info["pdf_errors"].append(
                        {
                            "mp_order_id": mp_order_id,
                            "channel_order_number": channel_order_number,
                            "connection_id": connection_id,
                            "reason": "generate_label_pdf_failed",
                            "exception": str(e),
                            "traceback": traceback.format_exc() if debug_mode else "",
                        }
                    )
                    if debug_mode:
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": "Lỗi khi generate_label_pdf_for_channel_order",
                                "mp_order_id": mp_order_id,
                                "channel_order_number": channel_order_number,
                                "connection_id": connection_id,
                                "exception": str(e),
                                "traceback": traceback.format_exc(),
                                "debug": debug_info,
                            },
                            status=500,
                        )
                    continue

        # --- Lưu file đơn lẻ (nếu mới generate) ---
        # Nếu lấy từ file cũ thì không cần ghi đè, nhưng ghi đè cũng không sao để update timestamp
        try:
            with open(bill_path, "wb") as f:
                f.write(pdf_bytes)
            debug_info["generated_files"].append(bill_path)
        except Exception as e:
            debug_info["pdf_errors"].append(
                {
                    "mp_order_id": mp_order_id,
                    "channel_order_number": channel_order_number,
                    "reason": "cannot_write_file",
                    "exception": str(e),
                    "traceback": traceback.format_exc() if debug_mode else "",
                }
            )
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi lưu file PDF",
                        "mp_order_id": mp_order_id,
                        "channel_order_number": channel_order_number,
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )
            continue


        # --- UPDATE FULFILLMENT PACKING STATUS ---
        # Handle case where Sapo MP and Sapo Core are not yet synced
        try:
            dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
            
            # Check if dto exists and has tracking code (from MP) but no fulfillments yet
            if dto and not dto.fulfillments:
                # Sync order from MP to ensure fulfillments are created
                debug_print(f"⚠️ No fulfillments for order {channel_order_number}, syncing...")
                try:
                    from core.sapo_client import get_sapo_client
                    sapo = get_sapo_client()
                    
                    # Ensure marketplace session is initialized
                    _ = sapo.marketplace  # This will trigger _ensure_tmdt_headers()
                    
                    # Sync the order using tmdt_session
                    sync_url = f"https://market-place.sapoapps.vn/v2/orders/sync?ids={mp_order_id}&accountId=319911"
                    sync_response = sapo.tmdt_session.put(sync_url)
                    
                    if sync_response.status_code == 200:
                        debug_print(f"✅ Synced order {mp_order_id} successfully")
                    else:
                        debug_print(f"⚠️ Sync returned status {sync_response.status_code}")

                    
                    # Wait and retry to check if fulfillments are created
                    import time
                    max_retries = 5
                    retry_delay = 2.0
                    
                    for retry in range(max_retries):
                        time.sleep(retry_delay)
                        dto = core_service.get_order_dto_from_shopee_sn(channel_order_number)
                        
                        if dto and dto.fulfillments:
                            debug_print(f"✅ Fulfillments created after sync (retry {retry + 1})")
                            break
                        else:
                            debug_print(f"⏳ Waiting for fulfillments... (retry {retry + 1}/{max_retries})")
                    
                except Exception as sync_error:
                    debug_print(f"❌ Sync error: {sync_error}")
                    debug_info.setdefault("logs", []).append(f"Sync error: {sync_error}")
            
            
            # Get package count (split) and resolve shipping carrier from Shopee
            split_count = None
            resolved_carrier = None
            
            try:
                from orders.services.shopee_print_service import ShopeeClient, _load_shipping_channels
                from core.system_settings import get_shop_by_connection_id
                
                shop_cfg = get_shop_by_connection_id(connection_id)
                if shop_cfg:
                    shop_name = shop_cfg["name"]
                    client = ShopeeClient(shop_name)
                    
                    # Get Shopee order info (returns Dict with order_id, buyer_name, etc.)
                    shopee_order_info = client.get_shopee_order_id(channel_order_number)
                    shopee_order_id = shopee_order_info["order_id"]
                    
                    # Add shop_name and connection_id for email API call
                    shopee_order_info["shop_name"] = shop_name
                    shopee_order_info["connection_id"] = connection_id
                    
                    logger.debug(f"✅ Got Shopee order ID: {shopee_order_id}")
                    
                    # Auto-update customer info from Shopee data (non-blocking)
                    if pdf_bytes and dto and dto.customer_id:
                        try:
                            from orders.services.customer_update_helper import update_customer_from_shopee_data
                            update_customer_from_shopee_data(
                                customer_id=dto.customer_id,
                                shopee_order_info=shopee_order_info,
                                pdf_bytes=pdf_bytes
                            )
                        except Exception as e:
                            logger.warning(f"Customer auto-update failed (non-blocking): {e}")
                    
                    package_info = client.get_package_info(shopee_order_id)
                    package_list = package_info.get("package_list", [])
                    split_count = len(package_list) if package_list else 1
                    debug_print(f"📦 Package count (split): {split_count}")
                    
                    # Resolve shipping carrier name from channels mapping file
                    if package_list:
                        first_pack = package_list[0]

                        channel_id = first_pack.get("fulfillment_channel_id") or first_pack.get("checkout_channel_id")
                        
                        # Load shipping channels map from JSON
                        channels_map = _load_shipping_channels()
                        base_carrier = meta.get("shipping_carrier") or ""
                        resolved_carrier = base_carrier  # Start with base value
                        
                        if not resolved_carrier and channels_map and channel_id:
                            # Try to get from JSON mapping
                            ch = channels_map.get(int(channel_id))
                            if ch:
                                resolved_carrier = ch.get("display_name") or ch.get("name")
                                debug_print(f"🚚 Resolved DVVC from channels file: {resolved_carrier}")
                        
                        if not resolved_carrier:
                            # Fallback to package data
                            resolved_carrier = (
                                first_pack.get("fulfillment_carrier_name")
                                or first_pack.get("checkout_carrier_name")
                                or ""
                            )
                            debug_print(f"🚚 Fallback DVVC from package: {resolved_carrier}")
                        
                        debug_print(f"🚚 Final shipping carrier: {resolved_carrier}")
                        
            except Exception as split_error:
                debug_print(f"⚠️ Could not get split count or resolve carrier: {split_error}")
                split_count = None
                resolved_carrier = meta.get("shipping_carrier") or ""
                
                # Fallback: Update customer from PDF only (cho express orders không phải Shopee)
                if pdf_bytes and dto and dto.customer_id:
                    try:
                        from orders.services.customer_update_helper import update_customer_from_pdf_only
                        logger.debug(f"Express order - updating customer from PDF only (order: {channel_order_number})")
                        update_customer_from_pdf_only(
                            customer_id=dto.customer_id,
                            pdf_bytes=pdf_bytes
                        )
                    except Exception as e:
                        logger.warning(f"Customer auto-update from PDF failed (non-blocking): {e}")
            
            # Now update packing status if fulfillments exist
            if dto and dto.fulfillments and len(dto.fulfillments) > 0:
                last_ff = dto.fulfillments[-1]
                if last_ff.id and dto.id:
                    # Kiểm tra packing_status hiện tại
                    current_packing_status = dto.packing_status or 0
                    
                    # Chỉ update nếu packing_status < 2 (giữ nguyên nếu >= 2)
                    if current_packing_status < 2:
                        # Use resolved carrier name (already resolved above)
                        shipping_carrier_name = resolved_carrier or meta.get("shipping_carrier") or ""
                        
                        success = core_service.update_fulfillment_packing_status(
                            order_id=dto.id,
                            fulfillment_id=last_ff.id,
                            packing_status=1,
                            shopee_id=channel_order_number,  # Shopee order number
                            split=split_count,  # Package count
                            dvvc=shipping_carrier_name  # Shipping carrier name (resolved)
                        )
                        if success:
                            debug_print(f"✅ Updated fulfillment {last_ff.id} with packing_status=1, shopee_id={channel_order_number}, split={split_count}, dvvc={shipping_carrier_name}")
                            debug_info.setdefault("logs", []).append(
                                f"Updated fulfillment {last_ff.id}: packing_status=1, shopee_id={channel_order_number}, split={split_count}, dvvc={shipping_carrier_name}"
                            )
                    else:
                        # Giữ nguyên packing_status hiện tại (>= 2)
                        debug_print(f"⏭️ Skipped updating packing_status for fulfillment {last_ff.id}: current status={current_packing_status} (>= 2, keeping unchanged)")
                        debug_info.setdefault("logs", []).append(
                            f"Skipped updating packing_status for {channel_order_number}: current status={current_packing_status} (>= 2, keeping unchanged)"
                        )
            else:
                debug_print(f"⚠️ Cannot update packing_status: fulfillments still not available after sync")
                debug_info.setdefault("logs", []).append(
                    f"Cannot update packing_status for {channel_order_number}: fulfillments not available"
                )
                
        except Exception as e:
            debug_print(f"❌ Update packing_status error: {e}")
            debug_info.setdefault("logs", []).append(f"Update packing_status error: {e}")



        # --- Gộp vào writer chung để trả về browser ---
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            debug_info["pdf_errors"].append(
                {
                    "mp_order_id": mp_order_id,
                    "channel_order_number": channel_order_number,
                    "reason": "cannot_read_or_merge_pdf",
                    "exception": str(e),
                    "traceback": traceback.format_exc() if debug_mode else "",
                }
            )
            if debug_mode:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Lỗi khi đọc/gộp PDF",
                        "mp_order_id": mp_order_id,
                        "channel_order_number": channel_order_number,
                        "exception": str(e),
                        "traceback": traceback.format_exc(),
                        "debug": debug_info,
                    },
                    status=500,
                )
            continue

    # ------------------------------------------------------------------
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

    output_buffer = BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)

    response = HttpResponse(
        output_buffer.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = 'inline; filename="shipping_labels.pdf"'
    response["Cache-Control"] = "no-store"
    return response


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
