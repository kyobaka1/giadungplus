# orders/services/shopee_dto.py
"""
Shopee-specific DTOs cho Shopee KNB API responses.
"""

from typing import List, Optional, Dict, Any
from pydantic import Field

from core.base.dto_base import BaseDTO


class ShopeePackageDTO(BaseDTO):
    """Package trong Shopee order"""
    package_number: str
    shipping_method: Optional[int] = None
    fulfillment_channel_id: Optional[int] = None
    checkout_channel_id: Optional[int] = None
    tracking_no: Optional[str] = None
    status: Optional[str] = None


class ShopeeOrderInfoDTO(BaseDTO):
    """Order info từ Shopee get_package API"""
    order_id: int
    order_sn: str
    package_list: List[ShopeePackageDTO] = Field(default_factory=list)


class ShopeePickupAddressDTO(BaseDTO):
    """Pickup address từ Shopee get_pickup API"""
    address_id: int
    full_address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None


class ShopeePickupTimeSlotDTO(BaseDTO):
    """Pickup time slot"""
    id: str
    value: str  # Unix timestamp string
    title: Optional[str] = None


class ShopeeSearchResultDTO(BaseDTO):
    """Result từ search bar hint API"""
    order_id: int
    order_sn: str


__all__ = [
    'ShopeePackageDTO',
    'ShopeeOrderInfoDTO',
    'ShopeePickupAddressDTO',
    'ShopeePickupTimeSlotDTO',
    'ShopeeSearchResultDTO',
]
