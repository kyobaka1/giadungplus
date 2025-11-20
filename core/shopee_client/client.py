# core/shopee_client/client.py
"""
Shopee KNB (Kênh Người Bán) Client.
Quản lý multi-shop với cookie switching.
"""

from typing import Optional, Dict, Any
import logging

import requests

from core.system_settings import (
    get_shop_by_connection_id,
    load_shopee_shops_detail,
)

from .repository import ShopeeRepository
from .cookie_manager import ShopeeCookieManager

logger = logging.getLogger(__name__)


class ShopeeClient:
    """
    Shopee KNB client với multi-shop support.
    
    Mỗi shop có cookie riêng được quản lý bởi ShopeeCookieManager.
    Client có thể switch giữa các shops để xử lý đơn từ shop khác nhau.
    
    Usage:
        # Initialize with shop
        client = ShopeeClient(shop_key="giadungplus_official")
        
        # hoặc với connection_id
        client = ShopeeClient(shop_key=10925)
        
        # Search order
        result = client.repo.search_order_raw("25112099T2CASS")
        
        # Switch to another shop
        client.switch_shop("lteng_vn")
        
        # Get package info
        package = client.repo.get_package_raw(123456)
    """
    
    def __init__(self, shop_key: int | str):
        """
        Initialize Shopee client.
        
        Args:
            shop_key: Shop name (str) hoặc connection_id (int)
        """
        self.cookie_manager = ShopeeCookieManager()
        self.session = requests.Session()
        self.repository: Optional[ShopeeRepository] = None
        
        # Current shop info
        self.shop_name: Optional[str] = None
        self.shop_config: Optional[Dict[str, Any]] = None
        self.connection_id: Optional[int] = None
        self.seller_shop_id: Optional[int] = None
        
        # Switch to initial shop
        self.switch_shop(shop_key)
        
        logger.info(f"[ShopeeClient] Initialized with shop '{self.shop_name}'")
    
    def _resolve_shop_config(self, shop_key: int | str) -> Dict[str, Any]:
        """
        Tìm shop config từ shop_key.
        
        Args:
            shop_key: Shop name (str) hoặc connection_id (int)
            
        Returns:
            Shop config dict
            
        Raises:
            ValueError: Nếu không tìm thấy shop
        """
        key_str = str(shop_key)
        
        # Try as connection_id first
        if key_str.isdigit():
            cfg = get_shop_by_connection_id(int(key_str))
            if cfg:
                return cfg
        
        # Try as shop name
        shops_detail = load_shopee_shops_detail()
        if isinstance(shops_detail, dict):
            cfg = shops_detail.get(key_str)
            if cfg:
                return cfg
        
        raise ValueError(f"Shop not found for key: {shop_key}")
    
    def switch_shop(self, shop_key: int | str):
        """
        Chuyển sang shop khác.
        Load cookie mới và update repository.
        
        Args:
            shop_key: Shop name (str) hoặc connection_id (int)
        """
        # Get shop config
        self.shop_config = self._resolve_shop_config(shop_key)
        
        self.shop_name = self.shop_config.get("name")
        self.connection_id = int(self.shop_config.get("shop_connect", 0))
        self.seller_shop_id = int(self.shop_config.get("seller_shop_id", 0))
        
        # Load cookie
        headers_file = self.shop_config.get("headers_file")
        if not headers_file:
            raise ValueError(f"Shop '{self.shop_name}' has no headers_file configured")
        
        logger.debug(f"[ShopeeClient] Loading cookie from: {headers_file}")
        headers = self.cookie_manager.load_cookie(headers_file)
        
        # Update session
        self.session.headers.clear()
        self.session.headers.update(headers)
        
        # Recreate repository với session mới
        self.repository = ShopeeRepository(
            session=self.session,
            base_url="https://banhang.shopee.vn/api/v3"
        )
        
        logger.info(f"[ShopeeClient] Switched to shop '{self.shop_name}' (connection_id={self.connection_id})")
    
    @property
    def repo(self) -> ShopeeRepository:
        """
        Access repository (shorthand).
        
        Returns:
            ShopeeRepository instance
        """
        if not self.repository:
            raise RuntimeError("Repository not initialized. Call switch_shop() first.")
        return self.repository
    
    def get_shopee_order_id(self, order_sn: str) -> int:
        """
        Tìm Shopee order_id từ mã đơn.
        
        Args:
            order_sn: Mã đơn Shopee (vd: 25112099T2CASS)
            
        Returns:
            Shopee order_id
            
        Raises:
            RuntimeError: Nếu không tìm thấy order
        """
        logger.debug(f"[ShopeeClient] Getting order_id for: {order_sn}")
        
        result = self.repo.search_order_raw(order_sn)
        
        try:
            order_id = result["data"]["order_sn_result"]["list"][0]["order_id"]
            logger.debug(f"[ShopeeClient] Found order_id: {order_id}")
            return order_id
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Order not found: {order_sn}") from e
    
    def get_package_info(self, order_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin package/shipment.
        
        Args:
            order_id: Shopee order_id
            
        Returns:
            Package info dict
        """
        logger.debug(f"[ShopeeClient] Getting package info for order: {order_id}")
        
        result = self.repo.get_package_raw(order_id)
        return result.get("data", {}).get("order_info", {})
    
    def arrange_shipment(
        self,
        order_id: int,
        package_number: str,
        pickup_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Arrange shipment - tìm ship / chuẩn bị hàng.
        
        Args:
            order_id: Shopee order_id
            package_number: Package number
            pickup_time: Pickup time (optional, sẽ auto-get nếu None)
            
        Returns:
            Response from Shopee
        """
        logger.info(f"[ShopeeClient] Arranging shipment for order {order_id}")
        
        # Get pickup info
        pickup_result = self.repo.get_pickup_raw(order_id, package_number)
        pickup_data = pickup_result.get("data", {})
        address_id = pickup_data.get("pickup_address_id")
        channel_id = pickup_data.get("channel_id")
        
        if not address_id or not channel_id:
            raise RuntimeError(f"Failed to get pickup info for order {order_id}")
        
        # Get pickup time slots if not provided
        if not pickup_time:
            slots_result = self.repo.get_pickup_time_slots_raw(
                order_ids=str(order_id),
                address_id=address_id,
                channel_id=channel_id
            )
            time_slots = slots_result.get("data", {}).get("time_slots", [])
            if not time_slots:
                raise RuntimeError(f"No pickup time slots available for order {order_id}")
            pickup_time = time_slots[0]["value"]
        
        # Build payload
        payload = {
            "remark": "",
            "pickup_time": pickup_time,
            "pickup_address_id": address_id,
            "seller_real_name": "",
            "shipping_mode": "pickup",
            "group_info": {
                "group_shipment_id": 0,
                "primary_package_number": package_number,
                "package_list": [
                    {"order_id": order_id, "package_number": package_number}
                ]
            }
        }
        
        return self.repo.arrange_shipment_raw(payload)
