# orders/services/dto.py
"""
Data Transfer Objects (DTOs) using Pydantic cho tất cả entities trong hệ thống.
Provides automatic validation, JSON serialization, và type safety.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import Field, field_validator, computed_field

from core.base.dto_base import BaseDTO


# ========================= ADDRESS =========================

class AddressDTO(BaseDTO):
    """Địa chỉ (billing/shipping address)"""
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

    @computed_field
    @property
    def as_line(self) -> str:
        """
        Ghép address thành 1 dòng để hiển thị/in.
        Format: address1, ward, district, city
        """
        parts = [self.address1, self.ward, self.district, self.city]
        return ", ".join([p for p in parts if p])


# ========================= CUSTOMER =========================

class CustomerGroupDTO(BaseDTO):
    """Nhóm khách hàng"""
    id: Optional[int] = None
    name: Optional[str] = None
    name_translate: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None
    is_default: bool = False


class CustomerSaleOrderStatsDTO(BaseDTO):
    """Thống kê đơn hàng của khách"""
    total_sales: float = 0.0
    order_purchases: float = 0.0
    returned_item_quantity: float = 0.0
    net_quantity: float = 0.0
    last_order_on: Optional[str] = None  # ISO datetime string


class CustomerDTO(BaseDTO):
    """Khách hàng"""
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
    tags: List[str] = Field(default_factory=list)
    addresses: List[AddressDTO] = Field(default_factory=list)


# ========================= LINE ITEMS & DISCOUNTS =========================

class OrderLineDiscountDTO(BaseDTO):
    """Giảm giá cho từng line item"""
    source: str  # "manual", "promotion", etc.
    rate: float = 0.0
    value: float = 0.0
    amount: float = 0.0
    reason: Optional[str] = None


class OrderLineItemDTO(BaseDTO):
    """Sản phẩm trong đơn hàng"""
    id: int
    product_id: int
    variant_id: int
    product_name: str
    variant_name: str
    sku: str
    barcode: Optional[str] = None
    unit: Optional[str] = None
    variant_options: Optional[str] = None
    price: float
    quantity: float
    line_amount: float
    discount_amount: float = 0.0
    discount_value: float = 0.0
    discount_rate: float = 0.0
    discount_reason: Optional[str] = None
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    product_type: str = "normal"
    discount_items: List[OrderLineDiscountDTO] = Field(default_factory=list)


# ========================= FULFILLMENT & SHIPMENT =========================

class FulfillmentLineItemDTO(BaseDTO):
    """Line item trong fulfillment (đóng gói)"""
    id: int
    order_line_item_id: int
    product_id: int
    variant_id: int
    sku: str
    barcode: Optional[str] = None
    unit: Optional[str] = None
    variant_options: Optional[str] = None
    quantity: float
    base_price: float
    line_amount: float
    line_discount_amount: float = 0.0
    line_tax_amount: float = 0.0
    product_type: str = "normal"


class ShipmentDTO(BaseDTO):
    """Thông tin vận chuyển"""
    id: int
    delivery_service_provider_id: Optional[int] = None
    service_name: Optional[str] = None
    cod_amount: float = 0.0
    freight_amount: float = 0.0
    delivery_fee: float = 0.0
    tracking_code: Optional[str] = None
    tracking_url: Optional[str] = None
    note_raw: Optional[str] = None      # JSON string của packing data
    detail_raw: Optional[str] = None    # JSON string của shipment detail


class FulfillmentDTO(BaseDTO):
    """Fulfillment (đóng gói/vận chuyển)"""
    id: int
    stock_location_id: int
    code: str
    status: str
    total: float = 0.0
    total_discount: float = 0.0
    total_tax: float = 0.0
    packed_on: Optional[str] = None     # ISO datetime string
    shipped_on: Optional[str] = None
    received_on: Optional[str] = None
    payment_status: str = "unpaid"
    print_status: bool = False
    composite_fulfillment_status: Optional[str] = None
    fulfillment_line_items: List[FulfillmentLineItemDTO] = Field(default_factory=list)
    shipment: Optional[ShipmentDTO] = None


# ========================= ORDER DTO (main) =========================

class OrderDTO(BaseDTO):
    """
    Đơn hàng chính - DTO trung tâm của hệ thống.
    Chứa đầy đủ thông tin từ Sapo order.
    """
    
    # ===== Core fields =====
    id: int
    tenant_id: int
    location_id: int
    code: str
    
    # Timestamps (ISO string format)
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    issued_on: Optional[str] = None
    finalized_on: Optional[str] = None
    completed_on: Optional[str] = None
    cancelled_on: Optional[str] = None
    
    # Assignee
    account_id: Optional[int] = None
    assignee_id: Optional[int] = None
    
    # Customer
    customer_id: Optional[int] = None
    customer: Optional[CustomerDTO] = None
    
    # Addresses
    billing_address: Optional[AddressDTO] = None
    shipping_address: Optional[AddressDTO] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    
    # Channel info
    channel: Optional[str] = None           # "Sàn TMĐT - Shopee"
    reference_number: Optional[str] = None  # Mã đơn sàn TMĐT
    source_id: Optional[int] = None
    reference_url: Optional[str] = None
    
    # Status  
    status: Optional[str] = None                # finalized, completed, cancelled
    print_status: bool = False
    packed_status: Optional[str] = None         # packed, unpacked
    fulfillment_status: Optional[str] = None    # shipped, unshipped
    received_status: Optional[str] = None       # received, unreceived
    payment_status: Optional[str] = None        # paid, unpaid
    return_status: Optional[str] = None         # returned, unreturned
    
    # Money
    total: float = 0.0
    total_discount: float = 0.0
    total_tax: float = 0.0
    delivery_fee: float = 0.0
    order_discount_rate: float = 0.0
    order_discount_value: float = 0.0
    order_discount_amount: float = 0.0
    
    # Tags & notes
    tags: List[str] = Field(default_factory=list)
    note: str = ""
    
    # Line items & fulfillments
    order_line_items: List[OrderLineItemDTO] = Field(default_factory=list, alias="line_items")
    fulfillments: List[FulfillmentDTO] = Field(default_factory=list)
    
    # Raw data (backup)
    raw: Dict[str, Any] = Field(default_factory=dict)
    
    # ===== Packing data (extract từ shipment.note) =====
    packing_status: int = 0          # 0=chưa đóng, 1-3 = các giai đoạn đóng gói
    nguoi_goi: Optional[str] = None  # Username người đóng gói
    time_packing: Optional[str] = None
    dvvc: Optional[str] = None       # Đơn vị vận chuyển
    shopee_id: Optional[str] = None  # Shopee order ID
    time_print: Optional[str] = None
    split: int = 0                   # Đơn có split hay không
    time_chia: Optional[str] = None
    shipdate: Optional[str] = None
    nguoi_chia: Optional[str] = None
    
    # ===== Computed fields (deadline) =====
    ship_deadline_fast: Optional[datetime] = None     # Deadline object
    ship_deadline_fast_str: Optional[str] = None      # Format để hiển thị
    
    # ========================= Computed Properties =========================
    
    @computed_field
    @property
    def customer_name(self) -> str:
        """Tên khách hàng (ưu tiên từ billing_address)"""
        if self.billing_address and self.billing_address.full_name:
            return self.billing_address.full_name
        if self.customer:
            return self.customer.name
        return ""
    
    @computed_field
    @property
    def customer_phone(self) -> str:
        """SĐT khách hàng (ưu tiên từ billing_address)"""
        if self.billing_address and self.billing_address.phone_number:
            return self.billing_address.phone_number
        if self.customer and self.customer.phone_number:
            return self.customer.phone_number
        return ""
    
    @computed_field
    @property
    def shipping_address_line(self) -> str:
        """Địa chỉ giao hàng dạng 1 dòng"""
        return self.shipping_address.as_line if self.shipping_address else ""
    
    @computed_field
    @property
    def shop_name(self) -> str:
        """
        Lấy tên shop từ tags.
        Format: ["Shopee", "Shopee_giadungplus_official"] → "giadungplus_official"
        Default: "Gia Dụng Plus +"
        """
        if not self.tags:
            return "Gia Dụng Plus +"
        
        for tag in self.tags:
            if not isinstance(tag, str):
                continue
            if tag.startswith("Shopee_"):
                # Cắt phần sau "Shopee_"
                return tag.split("Shopee_", 1)[1].strip()
        
        return "Gia Dụng Plus +"
    
    @computed_field
    @property
    def line_items(self) -> List[OrderLineItemDTO]:
        """Alias cho order_line_items (backward compatibility)"""
        return self.order_line_items


# ========================= MARKETPLACE CONFIRM DTO =========================

class MarketplaceConfirmOrderDTO(BaseDTO):
    """
    DTO cho confirm đơn từ Marketplace (PUT /v2/orders/confirm).
    Dùng khi gọi API "tìm ship / chuẩn bị hàng".
    """
    connection_id: int          # Shop connection ID
    order_id: int              # Marketplace order ID
    pickup_time_id: Optional[str | int] = None  # Pickup time slot ID
    pick_up_type: int          # 1 = arrangeShipment, 2 = dropOff
    address_id: int            # Pickup address ID


# ========================= PRODUCT & VARIANT DTOs =========================

class VariantPriceDTO(BaseDTO):
    """Giá của variant theo price list"""
    id: int
    value: float
    included_tax_price: float
    name: str
    price_list_id: int


class VariantInventoryDTO(BaseDTO):
    """Tồn kho của variant theo location"""
    location_id: int
    variant_id: int
    on_hand: float = 0.0
    available: float = 0.0
    committed: float = 0.0
    incoming: float = 0.0
    mac: float = 0.0  # Moving average cost


class VariantImageDTO(BaseDTO):
    """Hình ảnh của variant/product"""
    id: int
    path: str
    full_path: str
    file_name: str
    is_default: bool = False
    position: Optional[int] = None
    size: Optional[float] = None


class VariantDTO(BaseDTO):
    """Variant (phân loại sản phẩm)"""
    id: int
    tenant_id: int
    product_id: int
    sku: str
    barcode: Optional[str] = None
    name: str
    opt1: Optional[str] = None
    opt2: Optional[str] = None
    opt3: Optional[str] = None
    unit: Optional[str] = None
    status: str = "active"
    sellable: bool = True
    product_type: str = "normal"
    variant_retail_price: float = 0.0
    variant_whole_price: float = 0.0
    variant_import_price: float = 0.0
    
    variant_prices: List[VariantPriceDTO] = Field(default_factory=list)
    inventories: List[VariantInventoryDTO] = Field(default_factory=list)
    images: List[VariantImageDTO] = Field(default_factory=list)


class ProductOptionDTO(BaseDTO):
    """Option của product (size, color, etc.)"""
    id: int
    name: str
    position: int
    values: List[str] = Field(default_factory=list)


class ProductDTO(BaseDTO):
    """Sản phẩm"""
    id: int
    tenant_id: int
    name: str
    status: str = "active"
    brand_id: Optional[int] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    category: Optional[str] = None
    category_code: Optional[str] = None
    description: Optional[str] = None
    tags: str = ""
    medicine: bool = False
    product_type: str = "normal"
    
    opt1: Optional[str] = None
    opt2: Optional[str] = None
    opt3: Optional[str] = None
    
    variants: List[VariantDTO] = Field(default_factory=list)
    options: List[ProductOptionDTO] = Field(default_factory=list)
    images: List[VariantImageDTO] = Field(default_factory=list)


# ========================= EXPORTS =========================

__all__ = [
    # Address
    'AddressDTO',
    
    # Customer
    'CustomerGroupDTO',
    'CustomerSaleOrderStatsDTO',
    'CustomerDTO',
    
    # Line items
    'OrderLineDiscountDTO',
    'OrderLineItemDTO',
    
    # Fulfillment
    'FulfillmentLineItemDTO',
    'ShipmentDTO',
    'FulfillmentDTO',
    
    # Order
    'OrderDTO',
    'MarketplaceConfirmOrderDTO',
    
    # Product
    'VariantPriceDTO',
    'VariantInventoryDTO',
    'VariantImageDTO',
    'VariantDTO',
    'ProductOptionDTO',
    'ProductDTO',
]
