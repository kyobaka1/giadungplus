# customers/services/dto.py
"""
Data Transfer Objects (DTOs) using Pydantic cho customer entities.
Provides automatic validation, JSON serialization, và type safety.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import Field, field_validator, computed_field

from core.base.dto_base import BaseDTO


# ========================= ADDRESS =========================

class CustomerAddressDTO(BaseDTO):
    """Địa chỉ khách hàng"""
    
    id: Optional[int] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    ward: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    zip_code: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    label: Optional[str] = None
    phone_number: Optional[str] = None
    status: Optional[str] = None
    
    @computed_field
    @property
    def as_line(self) -> Optional[str]:
        """
        Ghép address thành 1 dòng để hiển thị.
        Format: address1, ward, district, city
        """
        parts = [
            self.address1,
            self.ward,
            self.district,
            self.city
        ]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else None


# ========================= CUSTOMER GROUP =========================

class CustomerGroupDTO(BaseDTO):
    """Nhóm khách hàng"""
    
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    name: Optional[str] = None
    name_translate: Optional[str] = None
    status: Optional[str] = None
    is_default: bool = False
    default_payment_term_id: Optional[int] = None
    default_payment_method_id: Optional[int] = None
    default_tax_type_id: Optional[int] = None
    default_discount_rate: Optional[float] = None
    default_price_list_id: Optional[int] = None
    note: Optional[str] = None
    code: Optional[str] = None
    count_customer: Optional[int] = None
    type: Optional[str] = None
    group_type: Optional[str] = None
    condition_type: Optional[str] = None
    conditions: Optional[str] = None


# ========================= CUSTOMER NOTE =========================

class CustomerNoteDTO(BaseDTO):
    """Ghi chú của khách hàng"""
    
    id: Optional[int] = None
    tenant_id: Optional[int] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    account_id: Optional[int] = None
    content: Optional[str] = None
    status: Optional[str] = None


# ========================= CUSTOMER STATS =========================

class CustomerSaleOrderStatsDTO(BaseDTO):
    """Thống kê đơn hàng của khách"""
    
    total_sales: float = 0.0
    order_purchases: float = 0.0
    returned_item_quantity: float = 0.0
    net_quantity: float = 0.0
    last_order_on: Optional[str] = None


# ========================= CUSTOMER (main) =========================

class CustomerDTO(BaseDTO):
    """
    Khách hàng - DTO chính cho customer entity.
    
    Field Mapping Conventions (do Sapo không hỗ trợ custom fields):
    - website → short_name (tên rút gọn)
    - tax_number → processing_status ("0" hoặc "1" hoặc null)
    """
    
    # Core fields
    id: int
    tenant_id: Optional[int] = None
    default_location_id: Optional[int] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    code: Optional[str] = None
    name: str
    dob: Optional[str] = None
    sex: Optional[str] = None  # "female", "male", "other"
    description: Optional[str] = None
    # Ghi chú (raw text hoặc JSON string từ Sapo)
    note: Optional[str] = None
    email: Optional[str] = None
    fax: Optional[str] = None
    phone_number: Optional[str] = None
    
    # Mapped fields (sử dụng convention)
    tax_number: Optional[str] = None  # Actually: processing_status ("0"/"1"/null)
    website: Optional[str] = None     # Actually: short_name
    
    # Group and assignment
    customer_group_id: Optional[int] = None
    group_id: Optional[int] = None
    group_ids: List[int] = Field(default_factory=list)
    group_name: Optional[str] = None
    assignee_id: Optional[int] = None
    
    # Payment and pricing
    default_payment_term_id: Optional[int] = None
    default_payment_method_id: Optional[int] = None
    default_tax_type_id: Optional[int] = None
    default_discount_rate: Optional[float] = None
    default_price_list_id: Optional[int] = None
    
    # Tags and addresses
    tags: List[str] = Field(default_factory=list)
    addresses: List[CustomerAddressDTO] = Field(default_factory=list)
    
    # Nested objects
    customer_group: Optional[CustomerGroupDTO] = None
    sale_stats: Optional[CustomerSaleOrderStatsDTO] = None
    
    # Status and financials
    status: Optional[str] = None
    is_default: bool = False
    debt: float = 0.0
    apply_incentives: Optional[str] = None
    total_expense: Optional[float] = None
    
    # Computed properties for field mapping
    
    @computed_field
    @property
    def short_name(self) -> Optional[str]:
        """
        Tên rút gọn - parsed từ website field.
        
        Format:
        - New: "Short Name/username" → "Short Name"
        - Legacy: "Short Name" → "Short Name"
        """
        if not self.website:
            return None
        # Split by "/" and take first part
        return self.website.split('/')[0].strip()
    
    @computed_field
    @property
    def username(self) -> Optional[str]:
        """
        Shopee username - parsed từ website field.
        
        Format:
        - New: "Short Name/ngocvuongdn95" → "ngocvuongdn95"
        - Legacy: "Short Name" → None (chưa có username)
        """
        if not self.website or '/' not in self.website:
            return None
        parts = self.website.split('/', 1)
        return parts[1].strip() if len(parts) > 1 else None
    
    @computed_field
    @property
    def processing_status(self) -> Optional[str]:
        """
        Trạng thái xử lý - mapped từ tax_number field.
        "1" = đã xử lý, "0" hoặc null = chưa xử lý
        """
        return self.tax_number
    
    @computed_field
    @property
    def is_processed(self) -> bool:
        """
        Check nếu customer đã được xử lý bằng tools.
        """
        return self.tax_number == "1"
    
    @computed_field
    @property
    def primary_address(self) -> Optional[CustomerAddressDTO]:
        """
        Địa chỉ chính (địa chỉ đầu tiên có status active).
        """
        for addr in self.addresses:
            if addr.status == "active":
                return addr
        return self.addresses[0] if self.addresses else None
    
    @computed_field
    @property
    def primary_phone(self) -> Optional[str]:
        """
        SĐT ưu tiên (từ phone_number hoặc primary_address).
        """
        if self.phone_number:
            return self.phone_number
        if self.primary_address and self.primary_address.phone_number:
            return self.primary_address.phone_number
        return None
    
    def set_username(self, username: str) -> None:
        """
        Helper để set username vào website field.
        Updates website field với format: "short_name/username"
        
        Args:
            username: Shopee username (e.g., "ngocvuongdn95")
        """
        current_short_name = self.short_name or self.name or ""
        self.website = f"{current_short_name}/{username}"
    
    def to_sapo_update_dict(
        self,
        short_name: Optional[str] = None,
        processing_status: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Convert CustomerDTO sang dict để update Sapo.
        
        Args:
            short_name: Nếu provided, update vào website field (sẽ merge với username nếu có)
            processing_status: Nếu provided, update vào tax_number field
            **kwargs: Các fields khác cần update
            
        Returns:
            Dict format phù hợp cho Sapo update API
        """
        update_data = {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            **kwargs
        }
        
        # Map short_name → website (preserve username if exists)
        if short_name is not None:
            # If customer has username, preserve it
            if self.username:
                update_data["website"] = f"{short_name}/{self.username}"
            else:
                update_data["website"] = short_name
        
        # Map processing_status → tax_number
        if processing_status is not None:
            update_data["tax_number"] = processing_status
        
        # Include các fields có sẵn
        if self.email:
            update_data["email"] = self.email
        if self.sex:
            update_data["sex"] = self.sex
        if self.customer_group_id:
            update_data["customer_group_id"] = self.customer_group_id
        if self.tags:
            update_data["tags"] = self.tags
        if self.apply_incentives:
            update_data["apply_incentives"] = self.apply_incentives
        # ⭐ PRESERVE DESCRIPTION - rất quan trọng để không mất data
        if self.description:
            update_data["description"] = self.description
            
        return update_data
