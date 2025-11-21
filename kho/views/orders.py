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
import os
from io import BytesIO

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

# ==================== EXISTING VIEWS (đã có implementation đầy đủ) ====================

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
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 50, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", "sortBy": "ISSUED_AT", "orderBy": "desc", })

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

        # 4) Lọc đơn đã đóng gói (packing_status != 0)
        #packing_status được lưu trong shipment note, đã được parse vào OrderDTO
        if order_dto.packing_status and order_dto.packing_status != 0:
            debug_print(f"express_orders Skip order {o.get('id')} - Already packed (status={order_dto.packing_status})")
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
        # Option: đính luôn DTO để template muốn đào sâu thì xài
        o["sapo_order_dto"] = order_dto
        filtered_orders.append(o)

    context["orders"] = filtered_orders
    context["current_kho"] = current_kho
    return render(request, "kho/orders/order_express.html", context)


@login_required
def shopee_orders(request):
    """
    Đơn hoả tốc:
    - Lấy danh sách đơn từ Marketplace API (Sapo Marketplace)
    - Lọc theo kho đang chọn trong session (geleximco / toky)
    - Gắn thêm thông tin Sapo core order (location_id, shipment, customer...)
    """

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
    all_orders = []
    page = 1
    limit = 250
    
    while True:
        mp_filter = BaseFilter(params={ 
            "connectionIds": connection_ids, 
            "page": page, 
            "limit": limit, 
            "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", 
            "sortBy": "ISSUED_AT", 
            "orderBy": "desc", 
        })
        
        mp_resp = mp_service.list_orders(mp_filter)
        orders = mp_resp.get("orders", [])
        metadata = mp_resp.get("metadata", {})
        total = metadata.get("total", 0)
        
        all_orders.extend(orders)
        debug_print(f"shopee_orders fetched page {page}: {len(orders)} orders. Total so far: {len(all_orders)}/{total}")
        
        if not orders or len(all_orders) >= total:
            break
            
        page += 1
        
    mp_orders = all_orders
    debug_print(f"shopee_orders finished fetching. Total: {len(mp_orders)} orders")

    filtered_orders = []

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
            debug_print(f"shopee_orders Skip order {o.get('id')} - No sapo_order_id")
            continue

        try:
            order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
        except Exception as e:
            # Nếu lỗi gọi API / parse thì bỏ qua đơn này
            debug_print(f"shopee_orders Skip order {o.get('id')} - Error getting DTO: {e}")
            continue

        # 3) Lọc theo kho (location_id)
        # Location filter disabled to show all orders
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue

        # 3) Lọc theo packing_status
        if order_dto.packing_status and order_dto.packing_status != 0:
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
        filtered_orders.append(o)

    context["orders"] = filtered_orders[::-1]
    context["current_kho"] = current_kho

    return render(request, "kho/orders/shopee_orders.html", context)

# ==================== NEW VIEWS (templates mẫu đã tạo) ====================

@login_required
def sapo_orders(request):
    """
    Đơn Sapo:
    - Đơn sỉ, đơn giao ngoài, đơn Facebook/Zalo, đơn khách hàng quay lại
    - Lấy từ Sapo Core API (không phải Marketplace)
    - Tổng hợp xử lý, in đơn
    """
    context = {
        "title": "ĐƠN SAPO - GIA DỤNG PLUS",
        "orders": [],
        "current_kho": request.session.get("current_kho", "geleximco"),
    }
    # TODO: Lấy đơn từ Sapo Core API (không phải Marketplace)
    # Filter: location_id, status, source_id (để phân biệt đơn sỉ, Facebook/Zalo, etc.)
    return render(request, "kho/orders/sapo_orders.html", context)


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
                    shopee_order_id = client.get_shopee_order_id(channel_order_number)
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
            
            # Now update packing status if fulfillments exist
            if dto and dto.fulfillments and len(dto.fulfillments) > 0:
                last_ff = dto.fulfillments[-1]
                if last_ff.id and dto.id:
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
