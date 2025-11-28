# products/services/dto.py
"""
Data Transfer Objects (DTOs) for Products module.
Extends Sapo product/variant data with GDP custom metadata.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import Field, computed_field

from core.base.dto_base import BaseDTO


# ========================= METADATA STRUCTURES =========================

class VideoInfoDTO(BaseDTO):
    """Thông tin video"""
    url: Optional[str] = None
    title: Optional[str] = None


class NhanPhuInfoDTO(BaseDTO):
    """Thông tin nhãn phụ"""
    vi_name: Optional[str] = None      # Tên tiếng Việt
    en_name: Optional[str] = None      # Tên tiếng Anh
    description: Optional[str] = None  # Mô tả
    material: Optional[str] = None     # Chất liệu
    hdsd: Optional[str] = None         # Hướng dẫn sử dụng


class BoxInfoDTO(BaseDTO):
    """Thông tin thùng (master carton)"""
    full_box: Optional[int] = None         # Số cái/thùng
    length_cm: Optional[float] = None       # Chiều dài (cm)
    width_cm: Optional[float] = None        # Chiều rộng (cm)
    height_cm: Optional[float] = None       # Chiều cao (cm)


class PackedInfoDTO(BaseDTO):
    """Thông tin đóng gói 1 chiếc"""
    length_cm: Optional[float] = None          # Chiều dài (cm)
    width_cm: Optional[float] = None            # Chiều rộng (cm)
    height_cm: Optional[float] = None           # Chiều cao (cm)
    weight_with_box_g: Optional[float] = None   # Trọng lượng cả hộp (g)
    weight_without_box_g: Optional[float] = None  # Trọng lượng không hộp (g)
    converted_weight_g: Optional[float] = None    # Trọng lượng quy đổi = dài x rộng x cao / 6000 (g)


class PackagingInfoDTO(BaseDTO):
    """Thông tin đóng gói của variant (legacy - giữ để tương thích)"""
    # Thông tin hộp đơn lẻ
    box_length_cm: Optional[float] = None    # Chiều dài hộp (cm)
    box_width_cm: Optional[float] = None     # Chiều rộng hộp (cm)
    box_height_cm: Optional[float] = None    # Chiều cao hộp (cm)
    weight_with_box_g: Optional[float] = None    # Trọng lượng có bì (g)
    weight_without_box_g: Optional[float] = None # Trọng lượng không bì (g)
    converted_weight_g: Optional[float] = None   # Trọng lượng quy đổi (g)
    
    # Thông tin thùng (master carton)
    carton_length_cm: Optional[float] = None
    carton_width_cm: Optional[float] = None
    carton_height_cm: Optional[float] = None
    units_per_carton: Optional[int] = None   # Số sản phẩm/thùng


class ImportInfoDTO(BaseDTO):
    """Thông tin nhập hàng của variant (legacy - giữ để tương thích)"""
    china_price_cny: Optional[float] = None      # Giá nhập (CNY - Nhân dân tệ)
    supplier_sku: Optional[str] = None           # SKU nhà sản xuất
    import_model_sku: Optional[str] = None       # SKU-MODEL nhập khẩu (ref to customs data)


class WebsiteInfoDTO(BaseDTO):
    """Thông tin website của variant"""
    web_variant_ids: List[str] = Field(default_factory=list)  # List IDs trên websites


class VariantMetadataDTO(BaseDTO):
    """
    GDP metadata của 1 variant (lưu trong product.description).
    
    Mỗi variant có một bộ metadata riêng, được lưu centralized trong
    product.description field với format [GDP_META]{...}[/GDP_META].
    """
    id: int                                      # variant_id (để match với variant trong Sapo)
    
    # Thông tin bắt buộc mới
    price_tq: Optional[float] = None            # Giá nhân dân tệ (CNY)
    sku_tq: Optional[str] = None                 # SKU của nhà sản xuất (SKU phân loại TQ)
    name_tq: Optional[str] = None                # Tên/mô tả sản phẩm TQ (để mô tả độ dày, độ nặng cho NCC khi xuất đơn)
    box_info: Optional[BoxInfoDTO] = None        # Thông tin thùng (full_box, dài x rộng x cao)
    packed_info: Optional[PackedInfoDTO] = None  # Thông tin đóng gói 1 chiếc
    sku_model_xnk: Optional[str] = None          # SKU-MODEL-XNK (nhập khẩu)
    web_variant_id: List[str] = Field(default_factory=list)  # Danh sách ID variant trên website
    
    # Legacy fields (giữ để tương thích)
    import_info: Optional[ImportInfoDTO] = None
    packaging_info: Optional[PackagingInfoDTO] = None
    website_info: Optional[WebsiteInfoDTO] = None


class ProductMetadataDTO(BaseDTO):
    """
    GDP metadata của product (lưu trong product.description).
    
    Structure:
    {
        "description": "<html>...</html>",
        "videos": [{"url": "...", "title": "..."}],
        "video_primary": {"url": "...", "title": "..."},
        "nhanphu_info": {"vi_name": "...", "en_name": "...", ...},
        "warranty_months": 12,
        "variants": [
            {"id": 123, "price_tq": 50.0, "sku_tq": "...", ...},
            {"id": 456, "box_info": {...}, ...}
        ]
    }
    """
    # Thông tin bắt buộc mới
    description: Optional[str] = None            # Mô tả sản phẩm (HTML format)
    videos: List[VideoInfoDTO] = Field(default_factory=list)  # Danh sách videos
    video_primary: Optional[VideoInfoDTO] = None # Video chính
    nhanphu_info: Optional[NhanPhuInfoDTO] = None # Thông tin nhãn phụ
    warranty_months: Optional[int] = None         # Thời gian bảo hành (tháng)
    
    # Legacy fields (giữ để tương thích)
    web_product_id: Optional[str] = None         # ID trên website
    custom_description: Optional[str] = None     # Mô tả tùy chỉnh
    
    variants: List[VariantMetadataDTO] = Field(default_factory=list)


# ========================= PRODUCT & VARIANT DTOs =========================

class VariantPriceDTO(BaseDTO):
    """Giá của variant theo price list"""
    id: int
    price_list_id: int
    name: str                    # "Giá nhập", "Giá bán lẻ", "Giá MIN"...
    value: float
    included_tax_price: float


class VariantInventoryDTO(BaseDTO):
    """Tồn kho của variant theo location"""
    location_id: int
    variant_id: int
    on_hand: float = 0.0         # Tồn kho thực tế
    available: float = 0.0       # Tồn kho khả dụng
    committed: float = 0.0       # Đã cam kết (cho đơn hàng)
    incoming: float = 0.0        # Hàng đang về
    mac: float = 0.0            # Moving average cost (giá vốn trung bình)
    min_value: Optional[float] = None  # Tồn kho tối thiểu
    max_value: Optional[float] = None  # Tồn kho tối đa
    bin_location: Optional[str] = None  # Vị trí trong kho


class VariantImageDTO(BaseDTO):
    """Hình ảnh variant/product"""
    id: int
    path: str
    full_path: str
    file_name: str
    is_default: bool = False
    position: Optional[int] = None
    size: Optional[float] = None


class ProductVariantDTO(BaseDTO):
    """
    Variant (phân loại sản phẩm) - Extended with GDP metadata.
    
    Chứa đầy đủ thông tin Sapo + GDP metadata mở rộng.
    """
    # ===== Standard Sapo fields =====
    id: int
    tenant_id: int
    product_id: int
    sku: str
    barcode: Optional[str] = None
    name: str                    # Tên đầy đủ: "Product name - opt1 / opt2"
    opt1: Optional[str] = None   # Phân loại 1
    opt2: Optional[str] = None   # Phân loại 2
    opt3: Optional[str] = None   # Phân loại 3
    unit: Optional[str] = None   # Đơn vị: "cái", "hộp", "bộ"...
    status: str = "active"
    sellable: bool = True
    product_type: str = "normal"
    
    # Weight
    weight_value: float = 0.0
    weight_unit: str = "g"
    
    # Pricing
    variant_retail_price: float = 0.0
    variant_whole_price: float = 0.0
    variant_import_price: float = 0.0
    cost_price: Optional[float] = None
    
    # Relations
    variant_prices: List[VariantPriceDTO] = Field(default_factory=list)
    inventories: List[VariantInventoryDTO] = Field(default_factory=list)
    images: Optional[List[VariantImageDTO]] = Field(default_factory=list)  # Cho phép None từ API
    
    # ===== GDP Extended metadata =====
    # Parsed from parent product.description [GDP_META] section
    gdp_metadata: Optional[VariantMetadataDTO] = None
    
    @computed_field
    @property
    def total_inventory(self) -> float:
        """Tổng tồn kho tất cả locations"""
        return sum(inv.on_hand for inv in self.inventories)
    
    @computed_field
    @property
    def total_available(self) -> float:
        """Tổng tồn kho khả dụng tất cả locations"""
        return sum(inv.available for inv in self.inventories)


class ProductOptionDTO(BaseDTO):
    """Option của product (kích thước, màu sắc, etc.)"""
    id: int
    name: str                    # "Kích thước", "Màu sắc"...
    position: int
    values: List[str] = Field(default_factory=list)  # ["S", "M", "L"]


class ProductDTO(BaseDTO):
    """
    Product - Extended with GDP metadata.
    
    Chứa đầy đủ thông tin Sapo product + variants + GDP metadata.
    GDP metadata được lưu trong description field với format [GDP_META]...[/GDP_META].
    """
    # ===== Standard Sapo fields =====
    id: int
    tenant_id: int
    name: str
    status: str = "active"
    
    # Brand & Category
    brand_id: Optional[int] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    category: Optional[str] = None
    category_code: Optional[str] = None
    
    # Description (chứa GDP_META JSON)
    description: Optional[str] = None
    
    # Tags & Type
    tags: str = ""
    product_type: str = "normal"
    medicine: bool = False
    
    # Options
    opt1: Optional[str] = None   # Option name 1
    opt2: Optional[str] = None   # Option name 2
    opt3: Optional[str] = None   # Option name 3
    
    # Timestamps
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    
    # ===== Relations =====
    variants: List[ProductVariantDTO] = Field(default_factory=list)
    options: List[ProductOptionDTO] = Field(default_factory=list)
    images: Optional[List[VariantImageDTO]] = Field(default_factory=list)  # Cho phép None từ API
    
    # ===== GDP metadata =====
    # Parsed from description field [GDP_META]...[/GDP_META]
    gdp_metadata: Optional[ProductMetadataDTO] = None
    
    @computed_field
    @property
    def original_description(self) -> str:
        """
        Mô tả gốc (không bao gồm GDP_META marker).
        
        Returns:
            Description text với [GDP_META]...[/GDP_META] đã được remove
        """
        if not self.description:
            return ""
        # Remove [GDP_META]...[/GDP_META] to get original description
        import re
        return re.sub(r'\[GDP_META\].*?\[/GDP_META\]', '', self.description, flags=re.DOTALL).strip()
    
    @computed_field
    @property
    def variant_count(self) -> int:
        """Số lượng variants"""
        return len(self.variants)
    
    @computed_field
    @property
    def total_inventory_all_variants(self) -> float:
        """Tổng tồn kho của tất cả variants"""
        return sum(v.total_inventory for v in self.variants)


# ========================= EXPORTS =========================

__all__ = [
    # Metadata - New structures
    'VideoInfoDTO',
    'NhanPhuInfoDTO',
    'BoxInfoDTO',
    'PackedInfoDTO',
    
    # Metadata - Legacy (tương thích)
    'PackagingInfoDTO',
    'ImportInfoDTO',
    'WebsiteInfoDTO',
    'VariantMetadataDTO',
    'ProductMetadataDTO',
    
    # Product & Variant
    'VariantPriceDTO',
    'VariantInventoryDTO',
    'VariantImageDTO',
    'ProductVariantDTO',
    'ProductOptionDTO',
    'ProductDTO',
]
