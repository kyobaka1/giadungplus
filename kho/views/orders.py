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
    SapoMarketplaceOrderService,
    SapoCoreOrderService,
)
from orders.services.dto import OrderDTO
import os
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter  # pip install PyPDF2
from orders.services.sapo_service import SapoMarketplaceOrderService
from orders.services.dto import MarketplaceConfirmOrderDTO
from core.system_settings import is_geleximco_address
from orders.services.shopee_print_service import generate_label_pdf_for_channel_order
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

connection_ids = get_connection_ids()
LOCATION_BY_KHO = {
    "geleximco": 241737,  # HN
    "toky": 548744,       # HCM
}
BILL_DIR = "logs/bill"

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
    mp_service = SapoMarketplaceOrderService()
    core_service = SapoCoreOrderService()

    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)

    # Filter cho Marketplace orders
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 50, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", "shippingCarrierIds": "134097,1285481,108346,17426,60176,1283785,1285470,35696,47741,14895,1272209,176002", "sortBy": "ISSUED_AT", "orderBy": "desc", })

    mp_resp = mp_service.list_orders(mp_filter)
    mp_orders = mp_resp.get("orders", [])

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
            continue

        try:
            order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
        except Exception:
            # Nếu lỗi gọi API / parse thì bỏ qua đơn này
            continue

        # 3) Lọc theo kho (location_id)
        if allowed_location_id and order_dto.location_id != allowed_location_id:
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
    mp_service = SapoMarketplaceOrderService()
    core_service = SapoCoreOrderService()

    # Kho hiện tại từ session
    current_kho = request.session.get("current_kho", "geleximco")
    allowed_location_id = LOCATION_BY_KHO.get(current_kho)

    # Filter cho Marketplace orders
    mp_filter = BaseFilter(params={ "connectionIds": connection_ids, "page": 1, "limit": 250, "channelOrderStatus": "READY_TO_SHIP,RETRY_SHIP,PROCESSED", "shippingCarrierIds": "51237,1218211,68301,36287,1218210,4110,59778,3411,1236070,37407,4095,171067,4329,1270129,57740,1236040,55646,166180,1289173", "sortBy": "ISSUED_AT", "orderBy": "desc", })

    mp_resp = mp_service.list_orders(mp_filter)
    mp_orders = mp_resp.get("orders", [])

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
            continue

        try:
            order_dto: OrderDTO = core_service.get_order_dto(sapo_order_id)
        except Exception:
            # Nếu lỗi gọi API / parse thì bỏ qua đơn này
            continue

        # 3) Lọc theo kho (location_id)
        if allowed_location_id and order_dto.location_id != allowed_location_id:
            continue

        # 3) Lọc theo packing_status
        if order_dto.packing_status != 0:
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

    mp_service = SapoMarketplaceOrderService()

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

        # --- Gọi service generate PDF từ nguồn Shopee (Nguồn A) / marketplace ---
        try:
            shipping_carrier = meta.get("shipping_carrier") or ""
            pdf_bytes = generate_label_pdf_for_channel_order(
                connection_id=connection_id,
                channel_order_number=channel_order_number,
                shipping_carrier=shipping_carrier,
            )

        except Exception as e:
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

        # --- Lưu file đơn lẻ ---
        bill_path = os.path.join(BILL_DIR, f"{channel_order_number}.pdf")
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
