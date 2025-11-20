# orders/services/order_builder.py
from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
import datetime
from .dto import *

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# ----- Helpers parse -----

def _build_address(data: Optional[Dict[str, Any]]) -> Optional[AddressDTO]:
    if not data:
        return None
    return AddressDTO(
        id=data.get("id"),
        label=data.get("label"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        full_name=data.get("full_name"),
        address1=data.get("address1"),
        address2=data.get("address2"),
        email=data.get("email"),
        phone_number=data.get("phone_number"),
        country=data.get("country"),
        city=data.get("city"),
        district=data.get("district"),
        ward=data.get("ward"),
        zip_code=data.get("zip_code"),
        full_address=data.get("full_address"),
        address_level=data.get("address_level"),
    )


def _build_customer(data: Optional[Dict[str, Any]]) -> Optional[CustomerDTO]:
    if not data:
        return None

    # group
    cg_raw = data.get("customer_group") or {}
    group = CustomerGroupDTO(
        id=cg_raw.get("id"),
        name=cg_raw.get("name"),
        name_translate=cg_raw.get("name_translate"),
        code=cg_raw.get("code"),
        status=cg_raw.get("status"),
        is_default=cg_raw.get("is_default", False),
    ) if cg_raw else None

    # sale stats
    stats_raw = data.get("sale_order") or {}
    stats = CustomerSaleOrderStatsDTO(
        total_sales=float(stats_raw.get("total_sales", 0) or 0),
        order_purchases=float(stats_raw.get("order_purchases", 0) or 0),
        returned_item_quantity=float(stats_raw.get("returned_item_quantity", 0) or 0),
        net_quantity=float(stats_raw.get("net_quantity", 0) or 0),
        last_order_on=stats_raw.get("last_order_on"),
    ) if stats_raw else None

    # addresses
    addresses = [
        _build_address(a)
        for a in (data.get("addresses") or [])
    ]

    return CustomerDTO(
        id=data["id"],
        code=data.get("code", ""),
        name=data.get("name", ""),
        phone_number=data.get("phone_number"),
        email=data.get("email"),
        sex=data.get("sex"),
        tax_number=data.get("tax_number"),
        website=data.get("website"),
        group=group,
        sale_stats=stats,
        tags=data.get("tags") or [],
        addresses=addresses,
    )


def _build_line_discount_list(items: List[Dict[str, Any]]) -> List[OrderLineDiscountDTO]:
    return [
        OrderLineDiscountDTO(
            source=i.get("source", ""),
            rate=float(i.get("rate", 0) or 0),
            value=float(i.get("value", 0) or 0),
            amount=float(i.get("amount", 0) or 0),
            reason=i.get("reason"),
        )
        for i in (items or [])
    ]


def _build_order_line_items(data_list: List[Dict[str, Any]]) -> List[OrderLineItemDTO]:
    result: List[OrderLineItemDTO] = []
    for d in (data_list or []):
        result.append(
            OrderLineItemDTO(
                id=d["id"],
                product_id=d["product_id"],
                variant_id=d["variant_id"],
                product_name=d.get("product_name", ""),
                variant_name=d.get("variant_name", ""),
                sku=d.get("sku", ""),
                barcode=d.get("barcode"),
                unit=d.get("unit"),
                variant_options=d.get("variant_options"),
                price=float(d.get("price", 0) or 0),
                quantity=float(d.get("quantity", 0) or 0),
                line_amount=float(d.get("line_amount", 0) or 0),
                discount_amount=float(d.get("discount_amount", 0) or 0),
                discount_value=float(d.get("discount_value", 0) or 0),
                discount_rate=float(d.get("discount_rate", 0) or 0),
                discount_reason=d.get("discount_reason"),
                tax_rate=float(d.get("tax_rate", 0) or 0),
                tax_amount=float(d.get("tax_amount", 0) or 0),
                product_type=d.get("product_type", "normal"),
                discount_items=_build_line_discount_list(d.get("discount_items") or []),
            )
        )
    return result


def _build_fulfillment_line_items(data_list: List[Dict[str, Any]]) -> List[FulfillmentLineItemDTO]:
    result: List[FulfillmentLineItemDTO] = []
    for d in (data_list or []):
        result.append(
            FulfillmentLineItemDTO(
                id=d["id"],
                order_line_item_id=d["order_line_item_id"],
                product_id=d["product_id"],
                variant_id=d["variant_id"],
                sku=d.get("sku", ""),
                barcode=d.get("barcode"),
                unit=d.get("unit"),
                variant_options=d.get("variant_options"),
                quantity=float(d.get("quantity", 0) or 0),
                base_price=float(d.get("base_price", 0) or 0),
                line_amount=float(d.get("line_amount", 0) or 0),
                line_discount_amount=float(d.get("line_discount_amount", 0) or 0),
                line_tax_amount=float(d.get("line_tax_amount", 0) or 0),
                product_type=d.get("product_type", "normal"),
            )
        )
    return result


def _build_shipment(data: Optional[Dict[str, Any]]) -> Optional[ShipmentDTO]:
    if not data:
        return None
    return ShipmentDTO(
        id=data["id"],
        delivery_service_provider_id=data.get("delivery_service_provider_id"),
        service_name=data.get("service_name"),
        cod_amount=float(data.get("cod_amount", 0) or 0),
        freight_amount=float(data.get("freight_amount", 0) or 0),
        delivery_fee=float(data.get("delivery_fee", 0) or 0),
        tracking_code=data.get("tracking_code"),
        tracking_url=data.get("tracking_url"),
        note_raw=data.get("note"),
        detail_raw=data.get("detail"),
    )


def _build_fulfillments(data_list: List[Dict[str, Any]]) -> List[FulfillmentDTO]:
    result: List[FulfillmentDTO] = []
    for d in (data_list or []):
        fl_items = _build_fulfillment_line_items(d.get("fulfillment_line_items") or [])
        shipment = _build_shipment(d.get("shipment"))

        result.append(
            FulfillmentDTO(
                id=d["id"],
                stock_location_id=d.get("stock_location_id"),
                code=d.get("code", ""),
                status=d.get("status", ""),
                total=float(d.get("total", 0) or 0),
                total_discount=float(d.get("total_discount", 0) or 0),
                total_tax=float(d.get("total_tax", 0) or 0),
                packed_on=d.get("packed_on"),
                shipped_on=d.get("shipped_on"),
                received_on=d.get("received_on"),
                payment_status=d.get("payment_status", ""),
                print_status=bool(d.get("print_status", False)),
                fulfillment_line_items=fl_items,
                shipment=shipment,
            )
        )
    return result


def build_order_from_sapo(payload: Dict[str, Any]) -> OrderDTO:
    """
    Nhận JSON trả về từ /admin/orders/{id}.json
    (có key "order" bao ngoài) → OrderDTO.
    """
    raw_order = payload.get("order") or payload

    order_line_items = _build_order_line_items(raw_order.get("order_line_items") or [])
    fulfillments = _build_fulfillments(raw_order.get("fulfillments") or [])

    customer = _build_customer(raw_order.get("customer_data"))
    billing_addr = _build_address(raw_order.get("billing_address"))
    shipping_addr = _build_address(raw_order.get("shipping_address"))

    # ============ TÍNH SHIP DEADLINE FAST ============
    packing_data = _extract_packing_data(raw_order)

    created_on_raw = raw_order.get("created_on")  # dạng "2025-11-18T09:16:23Z" (UTC)
    ship_deadline_fast_dt = None
    ship_deadline_fast_str = None

    if created_on_raw:
        try:
            # Parse thời gian UTC từ Sapo
            # Ví dụ "2025-11-18T09:16:23Z"
            created_utc = datetime.datetime.strptime(
                created_on_raw, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)

            # Convert sang giờ Việt Nam
            created_local = created_utc.astimezone(TZ_VN).replace(tzinfo=None)

            # Tính deadline giao nhanh
            ship_deadline_fast_dt = get_fast_deadline(created_local)
            ship_deadline_fast_str = ship_deadline_fast_dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            # Nếu parse lỗi thì cứ để None, không phá flow
            ship_deadline_fast_dt = None
            ship_deadline_fast_str = None

    # ============ BUILD ORDER DTO ============

    return OrderDTO(
        id=raw_order["id"],
        tenant_id=raw_order["tenant_id"],
        location_id=raw_order["location_id"],
        code=raw_order.get("code", ""),

        created_on=raw_order.get("created_on"),
        modified_on=raw_order.get("modified_on"),
        issued_on=raw_order.get("issued_on"),

        account_id=raw_order.get("account_id"),
        assignee_id=raw_order.get("assignee_id"),

        customer_id=raw_order.get("customer_id"),
        customer=customer,

        billing_address=billing_addr,
        shipping_address=shipping_addr,

        channel=raw_order.get("channel"),
        reference_number=raw_order.get("reference_number"),
        source_id=raw_order.get("source_id"),
        reference_url=raw_order.get("reference_url"),

        status=raw_order.get("status"),
        print_status=bool(raw_order.get("print_status", False)),
        packed_status=raw_order.get("packed_status"),
        fulfillment_status=raw_order.get("fulfillment_status"),
        received_status=raw_order.get("received_status"),
        payment_status=raw_order.get("payment_status"),
        return_status=raw_order.get("return_status"),

        total=float(raw_order.get("total", 0) or 0),
        total_discount=float(raw_order.get("total_discount", 0) or 0),
        total_tax=float(raw_order.get("total_tax", 0) or 0),
        delivery_fee=float(raw_order.get("delivery_fee", 0) or 0),
        order_discount_rate=float(raw_order.get("order_discount_rate", 0) or 0),
        order_discount_value=float(raw_order.get("order_discount_value", 0) or 0),
        order_discount_amount=float(raw_order.get("order_discount_amount", 0) or 0),

        tags=raw_order.get("tags") or [],
        note=raw_order.get("note") or "",

        order_line_items=order_line_items,
        fulfillments=fulfillments,

        raw=raw_order,

        # >>> NEW: gắn deadline vào DTO
        ship_deadline_fast=ship_deadline_fast_dt,
        ship_deadline_fast_str=ship_deadline_fast_str,

        # >>> NEW: packing data (có thì lấy, không có dùng default 0/None)
        packing_status=int(packing_data.get("packing_status") or 0),
        nguoi_goi=packing_data.get("nguoi_goi"),
        time_packing=packing_data.get("time_packing"),
        dvvc=packing_data.get("dvvc"),
        shopee_id=packing_data.get("shopee_id"),
        time_print=packing_data.get("time_print"),
        split=int(packing_data.get("split") or 0),
        time_chia=packing_data.get("time_chia"),
        shipdate=packing_data.get("shipdate"),
        nguoi_chia=packing_data.get("nguoi_chia"),

    )




# Nếu anh đã có HOLIDAYS ở chỗ khác thì import, ở đây em để sẵn cho đúng cấu trúc
HOLIDAYS = {
    # "2025-01-01",
    # "2025-04-30",
    # ...
}

def is_non_workday(dt: datetime.datetime) -> bool:
    # Chủ nhật hoặc ngày nghỉ trong HOLIDAYS (định nghĩa giống api_kho_sumreport)
    return dt.weekday() == 6 or dt.date().isoformat() in HOLIDAYS  # Chủ nhật = 6


def next_business_day(dt: datetime.datetime) -> datetime.datetime:
    candidate = dt
    while is_non_workday(candidate):
        candidate += datetime.timedelta(days=1)
    return candidate


def get_fast_deadline(created_local: datetime.datetime) -> datetime.datetime:
    """
    created_local: thời gian tạo đơn theo GIỜ VIỆT NAM (UTC+7, naive hoặc tz=+7 đều được).
    Logic giống y hệt trong api_kho_sumreport:

    - Nếu 0h–<18h: deadline = 23:59:59 cùng ngày.
    - Nếu >=18h: deadline = 12:00 trưa ngày hôm sau.
    - Nếu deadline rơi vào Chủ nhật → đẩy sang thứ 2, 12:00.
    - Sau cùng chạy qua next_business_day để tránh ngày nghỉ.
    """
    if 0 <= created_local.hour < 18:
        # Trước 18h -> cuối ngày
        raw = created_local.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        # Sau 18h -> 12h trưa hôm sau
        raw = (created_local + datetime.timedelta(days=1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

    # Nếu đúng Chủ nhật thì ép sang thứ 2 12:00
    if raw.weekday() == 6:  # Sunday
        raw = (raw + datetime.timedelta(days=1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

    return next_business_day(raw)


def _extract_packing_data(raw_order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Đọc fulfillment mới nhất trong raw_order và trích packing data
    từ shipment.note (JSON đã rút gọn key).
    Nếu không có hoặc lỗi JSON -> trả về {}.
    """
    fulfillments_raw = raw_order.get("fulfillments") or []
    if not fulfillments_raw:
        return {}

    latest_fulfillment = fulfillments_raw[-1] or {}
    shipment = latest_fulfillment.get("shipment") or {}
    note = shipment.get("note") or ""

    # Giữ điều kiện cũ của anh: chỉ xử lý khi có dấu "}"
    if not note or "}" not in note:
        return {}

    try:
        data = json.loads(note)
    except (ValueError, TypeError, json.JSONDecodeError):
        # Note không phải JSON chuẩn thì bỏ qua, tránh crash
        return {}

    # Mapping ngược giống hàm mo_rong_gon cũ
    reverse_key_mapping = {
        "pks": "packing_status",
        "human": "nguoi_goi",
        "tgoi": "time_packing",
        "vc": "dvvc",
        "spid": "shopee_id",
        "tin": "time_print",
        "sp": "split",
        "sd": "shipdate",
        "tc": "time_chia",
        "nc": "nguoi_chia",
    }

    result: Dict[str, Any] = {}
    for key, value in data.items():
        new_key = reverse_key_mapping.get(key, key)
        result[new_key] = value

    return result
