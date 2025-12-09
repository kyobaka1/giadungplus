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

# Import Customer DTOs from customers module (single source of truth)
from customers.services.dto import (
    CustomerDTO,
    CustomerGroupDTO, 
    CustomerSaleOrderStatsDTO,
    CustomerAddressDTO,
)


# ========================= ADDRESS =========================

class AddressDTO(BaseDTO):
    """
    Địa chỉ (billing/shipping address).
    
    Note: Đây là AddressDTO cho orders. CustomerAddressDTO được import từ customers.
    Có thể merge sau nếu cần.
    """
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
# Customer DTOs are imported from customers.services.dto
# - CustomerDTO
# - CustomerGroupDTO
# - CustomerSaleOrderStatsDTO
# - CustomerAddressDTO



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
    product_id: Optional[int] = None  # Có thể None cho các line items đặc biệt (phí vận chuyển, chiết khấu...)
    variant_id: Optional[int] = None  # Có thể None cho các line items đặc biệt
    product_name: str = ""  # Có thể rỗng cho các line items đặc biệt
    variant_name: str = ""  # Có thể rỗng cho các line items đặc biệt
    sku: str = ""  # Có thể rỗng cho các line items đặc biệt
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
    shopee_variation_id: Optional[str] = None
    
    # Packsize fields
    is_packsize: bool = False
    pack_size_quantity: Optional[int] = None      # Số lượng trong pack
    pack_size_root_id: Optional[int] = None       # Variant ID gốc (đơn lẻ)
    
    # Composite fields
    composite_item_domains: List[Dict[str, Any]] = Field(default_factory=list)


# ========================= REAL ITEMS (Qui đổi từ combo/packsize) =========================

class RealItemDTO(BaseDTO):
    """
    Sản phẩm đơn lẻ sau khi qui đổi từ combo/packsize.
    Dùng cho việc đóng gói, in phiếu, tracking.
    """
    variant_id: int                    # ID variant đơn lẻ
    old_id: int = 0                    # ID variant gốc (combo/packsize) - 0 nếu là sản phẩm thường
    product_id: Optional[int] = None
    sku: str
    barcode: Optional[str] = None
    variant_options: Optional[str] = None
    quantity: float
    unit: str = "cái"
    product_name: str = ""             # Tên sản phẩm (lấy từ product_name, split '/')
    
    # Optional: Reference to ProductVariantDTO (lazy load khi cần)
    variant_dto: Optional[Any] = None  # Type: ProductVariantDTO (import sau để tránh circular import)


class GiftItemDTO(BaseDTO):
    """
    Quà tặng được tự động áp dụng cho đơn hàng dựa trên promotions.
    """
    variant_id: int
    variant_name: str
    quantity: int
    promotion_name: str  # Tên chương trình khuyến mãi áp dụng
    sku: Optional[str] = None  # SKU của variant
    unit: Optional[str] = None  # Đơn vị tính
    opt1: Optional[str] = None  # Option 1 (phân loại 1)
    trigger_variant_ids: List[int] = Field(default_factory=list)  # Danh sách variant_ids trigger quà tặng này


# ========================= FULFILLMENT & SHIPMENT =========================

class FulfillmentLineItemDTO(BaseDTO):
    """Line item trong fulfillment (đóng gói)"""
    id: int
    order_line_item_id: int
    product_id: Optional[int] = None  # Có thể None cho các line items đặc biệt (shipping, discount, etc.)
    variant_id: Optional[int] = None  # Có thể None cho các line items đặc biệt
    sku: str = ""  # Có thể empty nếu không có product/variant
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
    
    # Real items (qui đổi từ combo/packsize thành sản phẩm đơn lẻ)
    real_items: List[RealItemDTO] = Field(default_factory=list)
    
    # Gifts (quà tặng tự động từ promotions)
    gifts: List[GiftItemDTO] = Field(default_factory=list)
    
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
    
    @computed_field
    @property
    def is_marketplace_order(self) -> bool:
        """
        Xác định đơn hàng có phải là đơn sàn TMĐT hay không.
        
        Đơn sàn TMĐT (Shopee, Lazada, Tiktok, Tiki, Sendo...) phải thỏa mãn TẤT CẢ điều kiện:
        1. source_id trong danh sách: 6510687, 1880152, 1880149, 1880150, 2172553
        2. account_id = 319911
        3. reference_number không null/empty
        4. tags phải chứa tên sàn: "Shopee", "Tiktok", "Lazada", "Tiki", "Sendo"...
        
        Returns:
            True nếu là đơn sàn, False nếu là đơn ngoài sàn
        """
        # Danh sách source_id của các sàn TMĐT
        MARKETPLACE_SOURCE_IDS = {6510687, 1880152, 1880149, 1880150, 2172553}
        
        # Điều kiện 1: source_id phải trong danh sách
        if not self.source_id or self.source_id not in MARKETPLACE_SOURCE_IDS:
            return False
        
        # Điều kiện 2: account_id phải = 319911
        if self.account_id != 319911:
            return False
        
        # Điều kiện 3: reference_number phải tồn tại và không rỗng
        if not self.reference_number or not self.reference_number.strip():
            return False
        
        # Điều kiện 4: tags phải chứa tên sàn
        if not self.tags:
            return False
        
        # Danh sách tên sàn TMĐT (viết thường để so sánh không phân biệt hoa thường)
        MARKETPLACE_NAMES = {"shopee", "tiktok", "lazada", "tiki", "sendo"}
        
        # Kiểm tra tags có chứa tên sàn không (không phân biệt hoa thường)
        tags_str = " ".join(str(tag).lower() for tag in self.tags if tag)
        has_marketplace_tag = any(
            marketplace_name in tags_str 
            for marketplace_name in MARKETPLACE_NAMES
        )
        
        if not has_marketplace_tag:
            return False
        
        # Tất cả điều kiện đều thỏa mãn -> đơn sàn
        return True
    
    @computed_field
    @property
    def is_offline_order(self) -> bool:
        """Đơn ngoài sàn (ngược lại với is_marketplace_order)"""
        return not self.is_marketplace_order
    
    @computed_field
    @property
    def total_quantity(self) -> int:
        """
        Tổng số lượng sản phẩm từ real_items (exclude SKU='KEO').
        Dùng cho việc tính tổng số lượng đã qui đổi.
        """
        return sum(
            int(item.quantity) 
            for item in self.real_items 
            if item.sku != 'KEO'
        )
    
    @computed_field
    @property
    def source_name(self) -> str:
        """
        Lấy tên của order source từ source_id.
        
        Returns:
            Source name hoặc empty string nếu không tìm thấy
            
        Note:
            Cần load order sources trước khi sử dụng (gọi load_all_order_sources)
        """
        if not self.source_id:
            return ""
        
        # Import ở đây để tránh circular import
        try:
            from kho.services.order_source_service import get_source_name
            return get_source_name(self.source_id)
        except Exception:
            # Nếu không load được service, trả về empty string
            return ""


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
    'RealItemDTO',
    'GiftItemDTO',
    
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
