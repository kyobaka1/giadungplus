# orders/services/dto.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union

@dataclass
class AddressDTO:
    id: Optional[int] = None
    label: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    ward: Optional[str] = None
    zip_code: Optional[str] = None
    full_address: Optional[str] = None
    address_level: Optional[str] = None

    @property
    def as_line(self) -> str:
        """
        Ghép address1 + ward + district + city cho màn in / hiển thị.
        """
        parts = [self.address1, self.ward, self.district, self.city]
        return ", ".join([p for p in parts if p])


@dataclass
class CustomerGroupDTO:
    id: Optional[int] = None
    name: Optional[str] = None
    name_translate: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None
    is_default: bool = False


@dataclass
class CustomerSaleOrderStatsDTO:
    total_sales: float = 0.0
    order_purchases: float = 0.0
    returned_item_quantity: float = 0.0
    net_quantity: float = 0.0
    last_order_on: Optional[str] = None  # mày cần thì parse datetime sau


@dataclass
class CustomerDTO:
    id: int
    code: str
    name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    sex: Optional[str] = None
    tax_number: Optional[str] = None
    website: Optional[str] = None
    group: Optional[CustomerGroupDTO] = None
    sale_stats: Optional[CustomerSaleOrderStatsDTO] = None
    tags: List[str] = field(default_factory=list)
    addresses: List[AddressDTO] = field(default_factory=list)


# -------------------------------
# Line item / discount / gift...
# -------------------------------

@dataclass
class OrderLineDiscountDTO:
    source: str
    rate: float
    value: float
    amount: float
    reason: Optional[str] = None


@dataclass
class OrderLineItemDTO:
    id: int
    product_id: int
    variant_id: int
    product_name: str
    variant_name: str
    sku: str
    barcode: Optional[str]
    unit: Optional[str]
    variant_options: Optional[str]
    price: float
    quantity: float
    line_amount: float
    discount_amount: float
    discount_value: float
    discount_rate: float
    discount_reason: Optional[str] = None
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    product_type: str = "normal"
    discount_items: List[OrderLineDiscountDTO] = field(default_factory=list)


# -------------------------------
# Fulfillment / shipment
# -------------------------------

@dataclass
class FulfillmentLineItemDTO:
    id: int
    order_line_item_id: int
    product_id: int
    variant_id: int
    sku: str
    barcode: Optional[str]
    unit: Optional[str]
    variant_options: Optional[str]
    quantity: float
    base_price: float
    line_amount: float
    line_discount_amount: float
    line_tax_amount: float
    product_type: str = "normal"


@dataclass
class ShipmentDTO:
    id: int
    delivery_service_provider_id: Optional[int]
    service_name: Optional[str]
    cod_amount: float
    freight_amount: float
    delivery_fee: float
    tracking_code: Optional[str]
    tracking_url: Optional[str]
    note_raw: Optional[str] = None      # chuỗi JSON note
    detail_raw: Optional[str] = None    # chuỗi JSON detail


@dataclass
class FulfillmentDTO:
    id: int
    stock_location_id: int
    code: str
    status: str
    total: float
    total_discount: float
    total_tax: float
    packed_on: Optional[str]
    shipped_on: Optional[str]
    received_on: Optional[str]
    payment_status: str
    print_status: bool
    fulfillment_line_items: List[FulfillmentLineItemDTO] = field(default_factory=list)
    shipment: Optional[ShipmentDTO] = None


# -------------------------------
# Order DTO – trung tâm
# -------------------------------

@dataclass
class OrderDTO:
    # Core ID & mã đơn
    id: int
    tenant_id: int
    location_id: int
    code: str

    created_on: Optional[str]
    modified_on: Optional[str]
    issued_on: Optional[str]

    # Người phụ trách
    account_id: Optional[int]
    assignee_id: Optional[int]

    # Khách hàng
    customer_id: Optional[int]
    customer: Optional[CustomerDTO] = None

    # Địa chỉ
    billing_address: Optional[AddressDTO] = None
    shipping_address: Optional[AddressDTO] = None

    # Thông tin kênh bán
    channel: Optional[str] = None                  # "Sàn TMĐT - Shopee"
    reference_number: Optional[str] = None         # mã đơn sàn 2511183TCRUNBE
    source_id: Optional[int] = None                # connection / nguồn
    reference_url: Optional[str] = None

    # Trạng thái
    status: Optional[str] = None                   # finalized
    print_status: bool = False
    packed_status: Optional[str] = None
    fulfillment_status: Optional[str] = None
    received_status: Optional[str] = None
    payment_status: Optional[str] = None
    return_status: Optional[str] = None

    # Tiền
    total: float = 0.0
    total_discount: float = 0.0
    total_tax: float = 0.0
    delivery_fee: float = 0.0
    order_discount_rate: float = 0.0
    order_discount_value: float = 0.0
    order_discount_amount: float = 0.0

    # Tag / note
    tags: List[str] = field(default_factory=list)
    note: str = ""

    # Chi tiết đơn
    order_line_items: List[OrderLineItemDTO] = field(default_factory=list)
    fulfillments: List[FulfillmentDTO] = field(default_factory=list)

    # Raw để phòng khi sau cần tới
    raw: Dict[str, Any] = field(default_factory=dict)

    # NEW
    ship_deadline_fast: Optional[datetime.datetime] = None  # deadline (local time)
    ship_deadline_fast_str: Optional[str] = None  # format sẵn để in ra

    # --- PACKING DATA (new) ---
    packing_status: int = 0  # tương ứng "packing_status" / "pks"
    nguoi_goi: Optional[str] = None  # "human"
    time_packing: Optional[str] = None  # "tgoi" - nếu muốn có thể đổi sang datetime
    dvvc: Optional[str] = None  # "vc"
    shopee_id: Optional[str] = None  # "spid"
    time_print: Optional[str] = None  # "tin"
    split: int = 0  # "sp" - 0/1 hoặc int khác
    time_chia: Optional[str] = None  # "tc"
    shipdate: Optional[str] = None  # "sd"
    nguoi_chia: Optional[str] = None  # "nc"

    # -----------------------
    # Convenience property
    # -----------------------
    @property
    def customer_name(self) -> str:
        if self.billing_address and self.billing_address.full_name:
            return self.billing_address.full_name
        if self.customer:
            return self.customer.name
        return ""

    @property
    def customer_phone(self) -> str:
        if self.billing_address and self.billing_address.phone_number:
            return self.billing_address.phone_number
        return self.customer.phone_number if self.customer and self.customer.phone_number else ""

    @property
    def shipping_address_line(self) -> str:
        return self.shipping_address.as_line if self.shipping_address else ""

    @property
    def shop_name(self) -> str:
        """
        Lấy tên shop từ tags của Sapo order.
        Ví dụ:
          ["Shopee", "Shopee_Gia Dụng Plus +"] -> "Gia Dụng Plus +"
        Nếu không tìm thấy, trả về default: "Gia Dụng Plus +"
        """
        if not self.tags:
            return "Gia Dụng Plus +"

        for t in self.tags:
            if not isinstance(t, str):
                continue
            if t.startswith("Shopee_"):
                # Cắt phần sau "Shopee_"
                return t.split("Shopee_", 1)[1].strip()

        # Không match format nào thì dùng default
        return "Gia Dụng Plus +"

@dataclass
class MarketplaceConfirmOrderDTO:
    """
    DTO cho confirm đơn Marketplace (Shopee).
    - pickup_time_id có thể None nếu init không trả time_slot_list
    """
    connection_id: int
    order_id: int                # marketplace_id
    pickup_time_id: Optional[Union[int, str]]
    pick_up_type: int
    address_id: int



